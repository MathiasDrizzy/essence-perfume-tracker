"""Reparación quirúrgica de dos clases de datos sucios:

1. NON-PERFUME: listings cuyo título contiene palabras clave de productos que no
   son perfumes (desodorantes, shampoos, esmaltes…). Se eliminan solo cuando NO
   tienen concentración explícita en el título (si tiene EDP/EDT, podría ser un
   estuche con perfume + deo y se deja).

2. BAD-MATCH: listings cuyo title_raw normaliza correctamente Y cuya perfume_id
   apunta a un perfume distinto. Solo se re-matchean cuando podemos normalizar
   el título con _extract_brand (sin necesitar fallback_brand), para no romper
   productos legítimos cuya marca venía de la API del retailer y no está en el
   título.

Uso: uv run python -m scrapers.migrate_rematch [--dry-run]
"""
from __future__ import annotations

import re

import click
import structlog
from sqlalchemy import delete, select, text

from scrapers.db import session_scope
from scrapers.matcher import PerfumeCache, find_or_create
from scrapers.models import Listing, Perfume, PriceHistory
from scrapers.normalize import (
    NON_PERFUME_BLOCK,
    _extract_brand,
    _extract_concentration,
    _extract_volume,
    normalize,
)

log = structlog.get_logger()

# Concentraciones — si el título tiene alguna, probablemente es un estuche con perfume
_HAS_CONC = re.compile(
    r"\b(e\.?d\.?[pct]\.?|eau\s+de\s+(parfum|toilette|cologne)|parfum|colonia)\b",
    re.IGNORECASE,
)


def _is_non_perfume(title: str) -> bool:
    """True si el producto es claramente no-perfume (sin concentración en el título)."""
    if not NON_PERFUME_BLOCK.search(title):
        return False
    # Si además tiene EDP/EDT/etc., es un estuche → conservar
    return not _HAS_CONC.search(title)


def _can_self_normalize(title: str) -> bool:
    """True si podemos normalizar el título sin necesitar fallback_brand externo."""
    return bool(_extract_brand(title) and _extract_volume(title))


@click.command()
@click.option("--dry-run", is_flag=True, help="Mostrar cambios sin aplicarlos.")
@click.option("--retailer", default=None, help="Limitar a un retailer específico.")
def main(dry_run: bool, retailer: str | None) -> None:
    """Repara non-perfumes y bad-matches sin tocar productos válidos."""
    deleted_np = 0
    fixed = 0
    skipped_no_brand = 0
    unchanged = 0
    errors = 0

    with session_scope() as session:
        cache = PerfumeCache()
        cache.load(session)
        log.info("cache_loaded", size=len(cache.slug2id))

        q = select(Listing).where(Listing.active == True)  # noqa: E712
        if retailer:
            q = q.where(Listing.retailer == retailer)
        listings = session.execute(q).scalars().all()
        log.info("listings_to_process", count=len(listings))

        for listing in listings:
            # --- Paso 1: eliminar no-perfumes ---
            if _is_non_perfume(listing.title_raw):
                if not dry_run:
                    session.execute(
                        delete(PriceHistory).where(PriceHistory.listing_id == listing.id)
                    )
                    session.delete(listing)
                deleted_np += 1
                log.info(
                    "non_perfume_deleted",
                    retailer=listing.retailer,
                    title=listing.title_raw[:80],
                    dry_run=dry_run,
                )
                continue

            # --- Paso 2: re-match (solo si podemos normalizar sin fallback) ---
            if not _can_self_normalize(listing.title_raw):
                skipped_no_brand += 1
                continue

            norm = normalize(listing.title_raw)
            if norm is None:
                skipped_no_brand += 1
                continue

            try:
                with session.begin_nested():
                    correct_perfume = find_or_create(session, norm, cache=cache)
            except Exception as exc:
                errors += 1
                log.warning("rematch_error", title=listing.title_raw[:80], error=str(exc)[:120])
                continue

            if correct_perfume.id != listing.perfume_id:
                old_id = listing.perfume_id
                if not dry_run:
                    listing.perfume_id = correct_perfume.id
                fixed += 1
                log.info(
                    "listing_rematched",
                    retailer=listing.retailer,
                    title=listing.title_raw[:80],
                    old_perfume_id=old_id,
                    new_perfume_id=correct_perfume.id,
                    new_name=correct_perfume.name,
                    dry_run=dry_run,
                )
            else:
                unchanged += 1

        if not dry_run:
            orphans = session.execute(
                text("""
                    SELECT p.id FROM perfumes p
                    WHERE NOT EXISTS (
                        SELECT 1 FROM listings l WHERE l.perfume_id = p.id AND l.active
                    )
                """)
            ).scalars().all()
            if orphans:
                session.execute(delete(Perfume).where(Perfume.id.in_(orphans)))
                log.info("orphans_cleaned", count=len(orphans))

    log.info(
        "rematch_done",
        deleted_non_perfume=deleted_np,
        fixed=fixed,
        skipped_no_brand=skipped_no_brand,
        unchanged=unchanged,
        errors=errors,
        dry_run=dry_run,
    )
    if not dry_run:
        print(
            f"\n✓ fixed={fixed}  deleted_np={deleted_np}  "
            f"skipped={skipped_no_brand}  unchanged={unchanged}  errors={errors}"
        )


if __name__ == "__main__":
    main()
