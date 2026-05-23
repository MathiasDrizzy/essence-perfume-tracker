"""Migración: limpia y fuzzy-mergea nombres de perfume.

Pasos por cada perfume:
1. Normalizar nombre: Title Case, strip SKU codes (ARMA105, FW162), strip
   paréntesis sin cerrar, strip sufijos basura (VARON, DAMA, HOMBRE suelto,
   "+15ML+SG75ML" etc.), colapsar whitespace.
2. Recomputar canonical_slug.
3. Dentro de (brand, volume_ml, concentration) → fuzzy match con threshold 92.
   Si dos perfumes hacen match → mergear el más nuevo en el más antiguo.

Conservador: solo mergea pairs MUY similares (score >= 92). No toca clones
(brand mal-asignada) — eso requiere otro pase.
"""

from __future__ import annotations

import re
from collections import defaultdict

import click
import structlog
from rapidfuzz import fuzz
from sqlalchemy import select, update

from scrapers.db import session_scope
from scrapers.models import Listing, Perfume
from scrapers.normalize import _slugify

log = structlog.get_logger()

FUZZY_THRESHOLD = 92

# Sufijos basura comunes a strippear del final del nombre.
TRAILING_NOISE = re.compile(
    r"\s*(?:"
    r"[A-Z]{2,5}\d{2,6}|"           # SKU codes: ARMA105, FW162, ABERBLUEV
    r"\(\s*\d+\s*\)|"                # "(2)" al final
    r"-\s*\d+|"                      # "- 1" al final
    r"\d+\s*$"                       # número suelto al final
    r")\s*$"
)

# Tokens basura al final del nombre (sueltos)
NAME_NOISE_PATTERNS = [
    r"\bvar[oó]n\b\s*$",            # "VARON" al final
    r"\bdama\b\s*$",
    r"\bhombre\b\s*$",
    r"\bmujer\b\s*$",
    r"\bunisex\b\s*$",
    r"\bmen\b\s*$",
    r"\bwomen\b\s*$",
    r"\s*\([^)]*$",                  # paréntesis abierto sin cerrar al final
    r"\s*\+\s*[\d.]+\s*ml.*$",       # "+ 15 ML + Gel..." etc
    r"\s*\+\s*\d+ml.*$",
    r"\s*\d+\s*ml\s*\+.*$",          # "100ml + Set"
    r"\beau\s+de\s*$",               # "Eau De" colgando
]


def normalize_name(raw: str) -> str:
    n = raw.strip()
    # Aplicar Title Case si está en MAYÚSCULAS
    if n.isupper() or sum(1 for c in n if c.isupper()) > len(n) * 0.5:
        n = n.title()
    # Stripping de patrones de ruido
    for pat in NAME_NOISE_PATTERNS:
        n = re.sub(pat, "", n, flags=re.IGNORECASE)
    # Trailing SKU/numeric codes
    while True:
        new_n = TRAILING_NOISE.sub("", n).strip()
        if new_n == n:
            break
        n = new_n
    # Colapsar whitespace y trim signos colgantes
    n = re.sub(r"\s+", " ", n).strip(" -,.|+")
    # Reparar paréntesis no balanceados eliminándolos
    open_p = n.count("(")
    close_p = n.count(")")
    if open_p != close_p:
        n = re.sub(r"[()]", "", n).strip()
    return n


def _new_slug(brand: str, name: str, conc: str | None, volume: int) -> str:
    return _slugify(f"{brand} {name} {conc or ''} {volume}")


def migrate(dry_run: bool = False) -> dict:
    stats = {
        "total": 0,
        "name_changed": 0,
        "merged_fuzzy": 0,
        "merged_exact": 0,
        "deleted": 0,
        "untouched": 0,
    }

    with session_scope() as session:
        perfumes: list[Perfume] = (
            session.execute(select(Perfume).order_by(Perfume.id)).scalars().all()
        )
        stats["total"] = len(perfumes)

        # Step 1: normalize all names + recompute slugs (in memory first).
        # Si normalize_name devuelve vacío, conservamos el nombre original
        # (mejor un nombre raro que perder el perfume y dejar su slug ocupado
        # sin tracking).
        cleaned: list[tuple[Perfume, str, str]] = []
        for p in perfumes:
            new_name = normalize_name(p.name) or p.name
            new_slug = _new_slug(p.brand, new_name, p.concentration, p.volume_ml)
            cleaned.append((p, new_name, new_slug))

        # Step 2: detect exact slug collisions (after rename) - merge
        slug_to_first: dict[str, int] = {}
        merges: list[tuple[int, int]] = []  # (from_id, to_id)
        for p, new_name, new_slug in cleaned:
            if new_slug in slug_to_first and slug_to_first[new_slug] != p.id:
                merges.append((p.id, slug_to_first[new_slug]))
            else:
                slug_to_first.setdefault(new_slug, p.id)

        # Step 3 — DESHABILITADO en favor de exact-slug-match only.
        # token_set_ratio resultó demasiado permisivo: confundía variantes genuinas
        # como "Cloud" vs "Cloud 2.0 Intense", o "212 VIP Rose" vs "212 VIP Women",
        # porque ignora tokens extras como "Intense", "2.0", "Women".
        # Solución conservadora: solo mergear cuando el slug post-normalización es
        # IDÉNTICO. Variantes genuinas se mantienen como perfumes separados.
        merged_already = {fid for fid, _ in merges}
        stats["merged_exact"] = len(merges)
        stats["merged_fuzzy"] = 0

        if dry_run:
            log.info("dry_run_preview", first_merges=merges[:5])
            log.info(
                "dry_run_normalizations",
                samples=[(p.name, n) for p, n, _ in cleaned[:5] if p.name != n],
            )
        else:
            # PHASE 1: merges (mover listings + borrar duplicados)
            for from_id, to_id in merges:
                session.execute(
                    update(Listing).where(Listing.perfume_id == from_id).values(perfume_id=to_id)
                )
                p_del = session.get(Perfume, from_id)
                if p_del:
                    session.delete(p_del)
                stats["deleted"] += 1
            session.flush()

            # PHASE 2: actualizar slugs a un valor TEMPORAL único primero, para evitar
            # colisiones cuando dos perfumes intercambian slugs durante el batch update.
            survivors = [(p, n, s) for p, n, s in cleaned if p.id not in merged_already]
            slug_changers = [
                (p, n, s) for p, n, s in survivors
                if p.canonical_slug != s
            ]
            for p, _, _ in slug_changers:
                p.canonical_slug = f"__migrating__{p.id}"
            session.flush()

            # PHASE 3: ahora aplicar los slugs reales (sin colisiones porque todos
            # los que iban a cambiar están en __migrating__)
            for p, new_name, new_slug in survivors:
                if p.name != new_name or p.canonical_slug != new_slug:
                    p.name = new_name
                    p.canonical_slug = new_slug
                    stats["name_changed"] += 1
            session.flush()

    return stats


@click.command()
@click.option("--dry-run", is_flag=True)
def main(dry_run: bool) -> None:
    stats = migrate(dry_run=dry_run)
    click.echo()
    click.echo("=== Name migration summary ===")
    for k, v in stats.items():
        click.echo(f"  {k:16} {v}")
    if dry_run:
        click.echo("\n(dry run — no changes written)")


if __name__ == "__main__":
    main()
