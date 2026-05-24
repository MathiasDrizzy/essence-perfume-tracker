"""Match de producto scrapeado → registro canónico en `perfumes`.

Estrategia:
1. Lookup directo por `canonical_slug` (caso normal).
2. Si no existe, fuzzy match contra perfumes de la misma marca + volumen
   (umbral 88 con rapidfuzz token_set_ratio).
3. Si tampoco hay match, inserta nuevo registro.

Cache: el `PerfumeCache` carga toda la tabla `perfumes` UNA vez al inicio de
la sesión y mantiene índices en memoria. Reduce N consultas SELECT a 1, lo
que acelera el cold-start de scrapers como silkperfumes (~22min → ~3min).
"""

from __future__ import annotations

from collections import defaultdict

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from scrapers.models import Perfume
from scrapers.normalize import NormalizedProduct

FUZZY_THRESHOLD = 88


class PerfumeCache:
    """Cache en memoria de la tabla `perfumes`.

    NO es thread-safe. Una instancia por session/scraper.
    Mantiene dos índices:
      - slug2id: canonical_slug → perfume_id (lookup directo O(1))
      - by_key: (brand_lower, volume_ml, concentration) → list[(name, id)]
        para fuzzy match O(n) sobre solo los candidatos del mismo group
    """

    def __init__(self) -> None:
        self.slug2id: dict[str, int] = {}
        self.by_key: dict[tuple[str, int, str | None], list[tuple[str, int]]] = defaultdict(list)
        self._loaded = False

    def load(self, session: Session) -> None:
        rows = session.execute(
            select(
                Perfume.id,
                Perfume.brand,
                Perfume.name,
                Perfume.volume_ml,
                Perfume.concentration,
                Perfume.canonical_slug,
            )
        ).all()
        for pid, brand, name, vol, conc, slug in rows:
            self.slug2id[slug] = pid
            self.by_key[(brand.lower(), vol, conc)].append((name, pid))
        self._loaded = True

    def find(self, norm: NormalizedProduct) -> int | None:
        """Retorna perfume.id si existe (exact slug o fuzzy match), None si no."""
        if norm.canonical_slug in self.slug2id:
            return self.slug2id[norm.canonical_slug]
        candidates = self.by_key.get((norm.brand.lower(), norm.volume_ml, norm.concentration))
        if not candidates:
            return None
        name_lower = norm.name.lower()
        best_score = 0
        best_id: int | None = None
        for cname, cid in candidates:
            score = fuzz.token_sort_ratio(cname.lower(), name_lower)
            if score >= FUZZY_THRESHOLD and score > best_score:
                best_score = score
                best_id = cid
        return best_id

    def add(self, pid: int, norm: NormalizedProduct) -> None:
        self.slug2id[norm.canonical_slug] = pid
        self.by_key[(norm.brand.lower(), norm.volume_ml, norm.concentration)].append(
            (norm.name, pid)
        )


def find_or_create(
    session: Session,
    norm: NormalizedProduct,
    cache: PerfumeCache | None = None,
) -> Perfume:
    """Devuelve el Perfume canónico para `norm`. Usa cache si está disponible."""
    if cache is not None:
        existing_id = cache.find(norm)
        if existing_id is not None:
            return session.get(Perfume, existing_id)
    else:
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
            score = fuzz.token_sort_ratio(c.name.lower(), norm.name.lower())
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
        perfume = session.execute(
            select(Perfume).where(Perfume.canonical_slug == norm.canonical_slug)
        ).scalar_one()
    else:
        perfume = session.execute(
            select(Perfume).where(Perfume.id == new_id)
        ).scalar_one()
    if cache is not None:
        cache.add(perfume.id, norm)
    return perfume
