"""Migración one-shot: aplica canonicalize_brand() a todos los perfumes existentes,
recomputa canonical_slug, y mergea perfumes duplicados que ahora resultan ser
el mismo (porque sus brands convergen al mismo canónico).

Proceso:
1. Para cada perfume → calcular nuevo (brand, slug)
2. Si nuevo slug ya existe en otra fila → mergear: mover sus listings a la
   fila más antigua (menor id), borrar la nueva
3. Si nuevo slug es único → solo UPDATE in place

Cómo correr:
    uv run python -m scrapers.migrate_brands [--dry-run]
"""

from __future__ import annotations

from collections import defaultdict

import click
import structlog
from sqlalchemy import select, update

from scrapers.db import session_scope
from scrapers.models import Listing, Perfume
from scrapers.normalize import (
    _slugify,
    canonicalize_brand,
)

log = structlog.get_logger()


def _recompute_slug(brand: str, name: str, concentration: str | None, volume_ml: int) -> str:
    return _slugify(f"{brand} {name} {concentration or ''} {volume_ml}")


def migrate(dry_run: bool = False) -> dict:
    stats = {
        "total": 0,
        "brand_changed": 0,
        "slug_changed": 0,
        "merged": 0,
        "deleted": 0,
        "untouched": 0,
    }

    with session_scope() as session:
        all_perfumes: list[Perfume] = session.execute(select(Perfume).order_by(Perfume.id)).scalars().all()
        stats["total"] = len(all_perfumes)
        # Slug existente → perfume_id "vivo" (el más antiguo gana)
        slug_to_id: dict[str, int] = {p.canonical_slug: p.id for p in all_perfumes}

        for p in all_perfumes:
            old_brand = p.brand
            new_brand = canonicalize_brand(old_brand) or old_brand
            new_slug = _recompute_slug(new_brand, p.name, p.concentration, p.volume_ml)

            brand_changed = new_brand != old_brand
            slug_changed = new_slug != p.canonical_slug

            if not brand_changed and not slug_changed:
                stats["untouched"] += 1
                continue

            if brand_changed:
                stats["brand_changed"] += 1
            if slug_changed:
                stats["slug_changed"] += 1

            # Si el nuevo slug ya existe en otra fila (que no sea esta) → mergeamos
            existing_id = slug_to_id.get(new_slug)
            if existing_id is not None and existing_id != p.id:
                # MERGE: mover listings de p → existing_id, luego borrar p
                if dry_run:
                    log.info("would_merge", from_id=p.id, into_id=existing_id, slug=new_slug)
                else:
                    session.execute(
                        update(Listing)
                        .where(Listing.perfume_id == p.id)
                        .values(perfume_id=existing_id)
                    )
                    # Borrar perfume duplicado (no tiene listings ya)
                    session.delete(p)
                stats["merged"] += 1
                stats["deleted"] += 1
                # Sacar slug viejo de mapping (este perfume ya no existe)
                slug_to_id.pop(p.canonical_slug, None)
                continue

            # Update in place
            if dry_run:
                log.info(
                    "would_update",
                    id=p.id,
                    brand=f"{old_brand} → {new_brand}" if brand_changed else old_brand,
                    slug=f"{p.canonical_slug} → {new_slug}" if slug_changed else p.canonical_slug,
                )
            else:
                # Quitar el slug viejo del mapping, agregar el nuevo
                slug_to_id.pop(p.canonical_slug, None)
                p.brand = new_brand
                p.canonical_slug = new_slug
                session.flush()
                slug_to_id[new_slug] = p.id

    return stats


@click.command()
@click.option("--dry-run", is_flag=True, help="Show what would happen, don't write")
def main(dry_run: bool) -> None:
    stats = migrate(dry_run=dry_run)
    click.echo()
    click.echo("=== Migration summary ===")
    for k, v in stats.items():
        click.echo(f"  {k:18} {v}")
    if dry_run:
        click.echo("\n(dry run — no changes written)")


if __name__ == "__main__":
    main()
