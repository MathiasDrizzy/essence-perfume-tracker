"""Migración: re-procesa listings con el normalizer actualizado.

Razón: el normalizer ANTIGUO confundía clones — productos como
"Armaf Victory Inspirado en Stronger With You Giorgio Armani" terminaban
categorizados bajo Giorgio Armani. El normalizer NUEVO (con PRE_BRAND_NOISE)
los detecta correctamente como Armaf, pero los perfumes ya en la DB no fueron
re-procesados.

Estrategia:
1. Para cada listing, re-aplicar normalize() sobre title_raw.
2. Si el normalize produce una marca distinta a la actual del perfume, mover
   el listing al perfume correcto (crear si no existe).
3. Al final, borrar perfumes huérfanos (sin listings).

Conservador: solo reasigna si el normalize NUEVO produce una marca canónica
distinta. No toca listings cuya re-normalización falle o coincida.
"""

from __future__ import annotations

from collections import defaultdict

import click
import structlog
from sqlalchemy import select, update

from scrapers.db import session_scope
from scrapers.matcher import find_or_create
from scrapers.models import Listing, Perfume
from scrapers.normalize import normalize

log = structlog.get_logger()


def migrate(dry_run: bool = False) -> dict:
    stats = {
        "listings_total": 0,
        "listings_reassigned": 0,
        "listings_unchanged": 0,
        "listings_skip_no_norm": 0,
        "perfumes_orphaned": 0,
        "perfumes_deleted": 0,
        "samples_reassigned": [],
    }

    with session_scope() as session:
        # Cargar todo en memoria
        listings = session.execute(select(Listing)).scalars().all()
        stats["listings_total"] = len(listings)

        for li in listings:
            norm = normalize(li.title_raw)
            if norm is None:
                stats["listings_skip_no_norm"] += 1
                continue

            current_perfume = session.get(Perfume, li.perfume_id)
            if current_perfume is None:
                continue

            # CRITERIO CONSERVADOR: solo reasignar si la BRAND canónica cambió.
            # No tocar listings cuyo brand calza pero slug es ligeramente distinto
            # (eso fragmenta el catálogo).
            if norm.brand == current_perfume.brand:
                stats["listings_unchanged"] += 1
                continue

            # Encontrar/crear el perfume canónico correcto
            if dry_run:
                if len(stats["samples_reassigned"]) < 10:
                    stats["samples_reassigned"].append({
                        "listing_id": li.id,
                        "retailer": li.retailer,
                        "title_raw": li.title_raw[:80],
                        "old_brand": current_perfume.brand,
                        "new_brand": norm.brand,
                        "old_slug": current_perfume.canonical_slug[:60],
                        "new_slug": norm.canonical_slug[:60],
                    })
                stats["listings_reassigned"] += 1
                continue

            new_perfume = find_or_create(session, norm)
            if new_perfume.id != li.perfume_id:
                li.perfume_id = new_perfume.id
                stats["listings_reassigned"] += 1
            else:
                stats["listings_unchanged"] += 1

        if not dry_run:
            session.flush()

            # Borrar perfumes huérfanos (sin listings activos)
            orphan_rows = session.execute(
                select(Perfume.id).where(
                    ~Perfume.id.in_(select(Listing.perfume_id).distinct())
                )
            ).all()
            orphan_ids = [r[0] for r in orphan_rows]
            stats["perfumes_orphaned"] = len(orphan_ids)
            for oid in orphan_ids:
                p = session.get(Perfume, oid)
                if p:
                    session.delete(p)
                    stats["perfumes_deleted"] += 1

    return stats


@click.command()
@click.option("--dry-run", is_flag=True)
def main(dry_run: bool) -> None:
    stats = migrate(dry_run=dry_run)
    click.echo()
    click.echo("=== Clone migration summary ===")
    samples = stats.pop("samples_reassigned", [])
    for k, v in stats.items():
        click.echo(f"  {k:24} {v}")
    if samples:
        click.echo("\n=== Sample reassignments ===")
        for s in samples:
            click.echo(f"  [{s['retailer']}] {s['title_raw']}")
            click.echo(f"     {s['old_brand']} → {s['new_brand']}")
            click.echo(f"     {s['old_slug']}  →  {s['new_slug']}")
    if dry_run:
        click.echo("\n(dry run — no changes written)")


if __name__ == "__main__":
    main()
