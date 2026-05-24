"""Base classes y pipeline para scrapers de tiendas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import UTC, datetime

import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from scrapers.db import session_scope
from scrapers.matcher import PerfumeCache, find_or_create
from scrapers.models import Listing, PriceHistory, ScrapeRun
from scrapers.normalize import normalize

log = structlog.get_logger()

# Cuántos rows de price_history acumular antes de hacer un INSERT bulk a Postgres.
# Reduce round-trips: N inserts individuales → N/PH_BATCH_SIZE inserts bulk.
PH_BATCH_SIZE = 100


class RawProduct(BaseModel):
    """Producto crudo emitido por un scraper antes de normalización."""
    model_config = ConfigDict(frozen=True)

    retailer: str
    retailer_sku: str | None = None
    url: str
    title: str
    price_clp: int
    list_price_clp: int | None = None
    in_stock: bool | None = None
    fallback_brand: str | None = None


class BaseScraper(ABC):
    retailer: str  # subclase debe setear

    @abstractmethod
    def fetch_products(self) -> Iterable[RawProduct]:
        """Yieldea productos crudos. Implementación específica por retailer."""

    def _upsert_listing(self, session, raw: "RawProduct", norm, cache: PerfumeCache | None = None) -> int:
        """Crea/actualiza perfume + listing y retorna listing.id.

        Usa UPSERT inline (`INSERT … ON CONFLICT DO UPDATE … RETURNING id`) en
        vez de SELECT + INSERT/UPDATE: reduce a 1 round-trip a Postgres por
        producto. Crítico para retailers grandes (productosdelujo 10k+).
        """
        perfume = find_or_create(session, norm, cache=cache)
        stmt = (
            pg_insert(Listing)
            .values(
                perfume_id=perfume.id,
                retailer=raw.retailer,
                retailer_sku=raw.retailer_sku,
                url=raw.url,
                title_raw=raw.title,
            )
            .on_conflict_do_update(
                index_elements=["retailer", "url"],
                set_={"perfume_id": perfume.id},
            )
            .returning(Listing.id)
        )
        return session.execute(stmt).scalar()

    @staticmethod
    def _flush_price_history(session, batch: list[dict]) -> None:
        """Inserta el batch acumulado de price_history en bulk."""
        if not batch:
            return
        stmt = (
            pg_insert(PriceHistory)
            .values(batch)
            .on_conflict_do_nothing(index_elements=["listing_id", "scraped_at"])
        )
        session.execute(stmt)

    def run(self) -> None:
        started = datetime.now(UTC)
        scraped = 0
        skipped = 0
        status = "ok"
        error: str | None = None

        with session_scope() as session:
            run = ScrapeRun(retailer=self.retailer, started_at=started, status="running")
            session.add(run)
            session.flush()
            run_id = run.id

        ph_batch: list[dict] = []
        try:
            with session_scope() as session:
                # Pre-cargar cache de perfumes existentes (1 SELECT vs N SELECTs)
                cache = PerfumeCache()
                cache.load(session)
                log.info("perfume_cache_loaded", retailer=self.retailer, size=len(cache.slug2id))

                for raw in self.fetch_products():
                    norm = normalize(raw.title, fallback_brand=raw.fallback_brand)
                    if norm is None:
                        skipped += 1
                        continue
                    listing_id: int | None = None
                    try:
                        with session.begin_nested():
                            listing_id = self._upsert_listing(session, raw, norm, cache=cache)
                        scraped += 1
                    except Exception as exc:
                        skipped += 1
                        log.warning(
                            "row_failed",
                            retailer=self.retailer,
                            title=raw.title[:80],
                            error=str(exc)[:200],
                        )
                        continue

                    # Acumular price_history para insert bulk
                    ph_batch.append({
                        "listing_id": listing_id,
                        "scraped_at": datetime.now(UTC),
                        "price_clp": raw.price_clp,
                        "list_price_clp": raw.list_price_clp,
                        "in_stock": raw.in_stock,
                    })
                    if len(ph_batch) >= PH_BATCH_SIZE:
                        try:
                            self._flush_price_history(session, ph_batch)
                        except Exception as exc:
                            log.warning(
                                "ph_batch_flush_failed",
                                retailer=self.retailer,
                                batch_size=len(ph_batch),
                                error=str(exc)[:200],
                            )
                        ph_batch.clear()

                # Flush final del batch restante
                if ph_batch:
                    try:
                        self._flush_price_history(session, ph_batch)
                    except Exception as exc:
                        log.warning(
                            "ph_final_flush_failed",
                            retailer=self.retailer,
                            error=str(exc)[:200],
                        )

        except Exception as exc:
            log.exception("scraper_failed", retailer=self.retailer)
            status = "failed"
            error = repr(exc)[:500]
            raise
        finally:
            with session_scope() as session:
                run = session.get(ScrapeRun, run_id)
                if run is not None:
                    run.finished_at = datetime.now(UTC)
                    run.products_scraped = scraped
                    run.status = status if scraped > 0 else ("partial" if status == "ok" else status)
                    run.error = error
            log.info(
                "scrape_done",
                retailer=self.retailer,
                scraped=scraped,
                skipped=skipped,
                status=status,
            )
