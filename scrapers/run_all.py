"""Orquestador del scraping diario — paralelizado.

Estrategia de paralelismo:
- Todos los scrapers HTTP-bound (Shopify, Paris API, Falabella, Sairam) corren en
  paralelo con un ThreadPool. Son independientes (cada uno abre su sesión HTTP y
  su sesión SQLAlchemy) y solo comparten la DB, donde los SAVEPOINT por producto
  + UPSERT por slug hacen el insert seguro entre runs concurrentes.
- Scrapers pesados (MercadoLibre con Playwright, Ripley con paginación larga)
  corren también en paralelo pero les damos su propio slot.
- max_workers configurable. Default 5 — equilibra throughput vs. memoria.
- Al final, verify_urls limpia muertos y luego dispara alertas Telegram.
"""

from __future__ import annotations

import asyncio
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import click
import structlog

from scrapers.alerts import check_and_send_alerts
from scrapers.verify_urls import verify_all

log = structlog.get_logger()


# Cada scraper se importa lazy en su runner para no cargar Playwright/Camoufox
# innecesariamente cuando se filtra con --only.
def _shopify_factory(site_key: str):
    """Construye un runner Shopify para un site específico."""
    def _runner() -> None:
        from scrapers.shopify import SHOPIFY_SITES, ShopifyScraper
        ShopifyScraper(site_key, SHOPIFY_SITES[site_key]).run()
    return _runner


def _sairam() -> None:
    from scrapers.jumpseller import JumpsellerScraper
    JumpsellerScraper().run()


def _paris() -> None:
    from scrapers.paris import ParisScraper
    ParisScraper().run()


def _ripley() -> None:
    from scrapers.ripley import RipleyScraper
    RipleyScraper().run()


def _falabella() -> None:
    from scrapers.falabella import FalabellaScraper
    FalabellaScraper().run()


# Cada Shopify site corre como tarea independiente en el ThreadPool. Antes
# tomaban ~35min en serie (silkperfumes 22min + productosdelujo 12min + …);
# ahora corren en paralelo y la duración total = MAX individual ≈ silkperfumes.
SCRAPERS: dict[str, callable] = {
    "silkperfumes": _shopify_factory("silkperfumes"),
    "productosdelujo": _shopify_factory("productosdelujo"),
    "multimarcasperfumes": _shopify_factory("multimarcasperfumes"),
    "alishaperfumes": _shopify_factory("alishaperfumes"),
    "eliteperfumes": _shopify_factory("eliteperfumes"),
    "lodoro": _shopify_factory("lodoro"),
    "sairam": _sairam,
    "paris": _paris,
    "ripley": _ripley,
    "falabella": _falabella,
}


@click.command()
@click.option(
    "--only",
    multiple=True,
    type=click.Choice(list(SCRAPERS.keys())),
    help="Run only specific scrapers (default: all). Repeatable.",
)
@click.option("--workers", type=int, default=6, help="Parallel scraper workers.")
@click.option("--skip-alerts", is_flag=True, help="Don't run alerts check at the end.")
@click.option("--skip-verify", is_flag=True, help="Don't run URL verifier at the end.")
def main(only: tuple[str, ...], workers: int, skip_alerts: bool, skip_verify: bool) -> None:
    """Run all scrapers (in parallel) + verifier + alerts."""
    started = time.time()
    targets = SCRAPERS if not only else {k: v for k, v in SCRAPERS.items() if k in only}
    log.info("orchestrator_start", scrapers=list(targets), workers=workers)

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scraper") as ex:
        futures = {ex.submit(runner): name for name, runner in targets.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                fut.result()
                log.info("scraper_finished", name=name)
            except Exception as exc:
                tb = traceback.format_exc()
                log.error("scraper_failed", name=name, error=str(exc)[:300], tb=tb[:600])
                failures.append(name)

    log.info("scrapers_phase_done", elapsed_sec=int(time.time() - started))

    if not skip_verify:
        try:
            stats = asyncio.run(verify_all(only_retailer=None, limit=None))
            log.info("verify_done", stats=stats)
        except Exception as exc:
            log.error("verify_failed", error=str(exc)[:300])
            failures.append("verify_urls")

    if not skip_alerts:
        try:
            n = asyncio.run(check_and_send_alerts())
            log.info("alerts_done", triggered=n)
        except Exception as exc:
            log.error("alerts_failed", error=str(exc)[:300])
            failures.append("alerts")

    total = int(time.time() - started)
    # Política de éxito: el workflow NO falla aunque uno o más scrapers individuales
    # caigan (Ripley/ML típicamente bloqueados desde IPs datacenter, por ej.). Solo
    # fallamos si verify_urls o alerts (la infraestructura propia) revientan, o si
    # NINGÚN scraper logró correr.
    infra_failures = [f for f in failures if f in ("verify_urls", "alerts")]
    scraper_failures = [f for f in failures if f not in ("verify_urls", "alerts")]
    successful_scrapers = len(targets) - len(scraper_failures)
    if infra_failures or successful_scrapers == 0:
        log.error(
            "orchestrator_done_with_failures",
            failures=failures,
            elapsed_sec=total,
        )
        sys.exit(1)
    if scraper_failures:
        log.warning(
            "orchestrator_done_with_partial_failures",
            scraper_failures=scraper_failures,
            successful=successful_scrapers,
            elapsed_sec=total,
        )
    else:
        log.info("orchestrator_done", elapsed_sec=total)


if __name__ == "__main__":
    main()
