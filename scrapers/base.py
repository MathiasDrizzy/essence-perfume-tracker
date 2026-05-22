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
from scrapers.matcher import find_or_create
from scrapers.models import Listing, PriceHistory, ScrapeRun
from scrapers.normalize import normalize

log = structlog.get_logger()


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

    def _upsert_one(self, session, raw: "RawProduct", norm) -> None:
        """Una pasada DB para un solo producto. Corre dentro de un SAVEPOINT."""
        perfume = find_or_create(session, norm)

        listing = session.execute(
            select(Listing).where(
                Listing.retailer == raw.retailer,
                Listing.url == raw.url,
            )
        ).scalar_one_or_none()
        if listing is None:
            listing = Listing(
                perfume_id=perfume.id,
                retailer=raw.retailer,
                retailer_sku=raw.retailer_sku,
                url=raw.url,
                title_raw=raw.title,
            )
            session.add(listing)
            session.flush()
        elif listing.perfume_id != perfume.id:
            # Re-bind si el perfume canónico cambió por mejor normalización.
            listing.perfume_id = perfume.id

        stmt = (
            pg_insert(PriceHistory)
            .values(
                listing_id=listing.id,
                scraped_at=datetime.now(UTC),
                price_clp=raw.price_clp,
                list_price_clp=raw.list_price_clp,
                in_stock=raw.in_stock,
            )
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

        try:
            with session_scope() as session:
                for raw in self.fetch_products():
                    norm = normalize(raw.title, fallback_brand=raw.fallback_brand)
                    if norm is None:
                        skipped += 1
                        continue
                    # SAVEPOINT por producto: si un único registro rompe (constraint,
                    # data corrupta), el resto del run sigue. La excepción se loguea
                    # y solo se pierde ese row.
                    try:
                        with session.begin_nested():
                            self._upsert_one(session, raw, norm)
                        scraped += 1
                    except Exception as exc:
                        skipped += 1
                        log.warning(
                            "row_failed",
                            retailer=self.retailer,
                            title=raw.title[:80],
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
