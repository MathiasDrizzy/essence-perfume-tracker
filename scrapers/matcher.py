"""Match de producto scrapeado → registro canónico en `perfumes`.

Estrategia:
1. Lookup directo por `canonical_slug` (caso normal).
2. Si no existe, fuzzy match contra perfumes de la misma marca + volumen
   (umbral 88 con rapidfuzz token_set_ratio).
3. Si tampoco hay match, inserta nuevo registro.
"""

from __future__ import annotations

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from scrapers.models import Perfume
from scrapers.normalize import NormalizedProduct

FUZZY_THRESHOLD = 88


def find_or_create(session: Session, norm: NormalizedProduct) -> Perfume:
    existing = session.execute(
        select(Perfume).where(Perfume.canonical_slug == norm.canonical_slug)
    ).scalar_one_or_none()
    if existing:
        return existing

    candidates = session.execute(
        select(Perfume).where(
            Perfume.brand.ilike(norm.brand),
            Perfume.volume_ml == norm.volume_ml,
            Perfume.concentration == norm.concentration,
        )
    ).scalars().all()

    best: tuple[Perfume, float] | None = None
    for c in candidates:
        score = fuzz.token_set_ratio(c.name.lower(), norm.name.lower())
        if score >= FUZZY_THRESHOLD and (best is None or score > best[1]):
            best = (c, score)
    if best:
        return best[0]

    # INSERT con ON CONFLICT DO NOTHING para soportar runs concurrentes que
    # podrían computar el mismo canonical_slug al mismo tiempo.
    stmt = (
        pg_insert(Perfume)
        .values(
            brand=norm.brand,
            name=norm.name,
            concentration=norm.concentration,
            volume_ml=norm.volume_ml,
            gender=norm.gender,
            canonical_slug=norm.canonical_slug,
        )
        .on_conflict_do_nothing(index_elements=["canonical_slug"])
        .returning(Perfume.id)
    )
    new_id = session.execute(stmt).scalar()
    if new_id is None:
        # Otro proceso lo insertó primero; lo recuperamos.
        return session.execute(
            select(Perfume).where(Perfume.canonical_slug == norm.canonical_slug)
        ).scalar_one()
    session.expire_all()
    return session.get(Perfume, new_id)
