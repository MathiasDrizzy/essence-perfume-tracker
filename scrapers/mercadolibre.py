"""Scraper para MercadoLibre Chile.

⚠️ MercadoLibre 2026: PolicyAgent bloquea el API público
(`api.mercadolibre.com/sites/MLC/search`) incluso con OAuth Client Credentials.
Solo Authorization Code (con login interactivo del usuario) destrabaría el endpoint
de búsqueda. Para evitar fricción, scrapeamos el listado web con Playwright + stealth.

Estrategia:
- listado.mercadolibre.cl/perfume paginado con `_Desde_N` (offset 1, 51, 101…)
- Playwright + playwright-stealth (la web detecta navegadores headless plain)
- Para que funcione, la máquina necesita IP **no-datacenter** (Mac residencial chilena).
  Desde GH Actions devuelve 0 productos (los 'suspicious-traffic') sin romper el workflow.

Si en el futuro hacemos Authorization Code flow para el API, ver `_oauth_search` abajo
como referencia.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable

import click
import structlog
from camoufox.async_api import AsyncCamoufox

from scrapers.base import BaseScraper, RawProduct
from scrapers.config import settings

log = structlog.get_logger()

BASE_URL = "https://listado.mercadolibre.cl/perfume"
PAGE_SIZE = 50
MAX_PAGES_DEFAULT = 40  # ~2000 productos


class MercadoLibreScraper(BaseScraper):
    retailer = "mercadolibre"

    def __init__(self, max_pages: int | None = None) -> None:
        self.max_pages = max_pages or MAX_PAGES_DEFAULT

    def fetch_products(self) -> Iterable[RawProduct]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[RawProduct]:
        results: list[RawProduct] = []
        seen_urls: set[str] = set()
        # Camoufox = Firefox con stealth a nivel C++ (parchea Canvas, WebGL,
        # AudioContext, navigator props). Más resistente que Playwright stealth
        # contra "suspicious-traffic" landing de ML.
        async with AsyncCamoufox(
            headless=True,
            locale="es-CL",
            geoip=True,
            os=["macos"],
        ) as browser:
            page = await browser.new_page()
            consecutive_empty = 0
            for page_num in range(1, self.max_pages + 1):
                offset = (page_num - 1) * PAGE_SIZE + 1
                url = BASE_URL if page_num == 1 else f"{BASE_URL}_Desde_{offset}"

                cards = await self._load_with_retries(page, url)
                if not cards:
                    consecutive_empty += 1
                    log.warning("ml_empty_page", page=page_num, consecutive=consecutive_empty)
                    if consecutive_empty >= 2:
                        log.info("ml_stopping_after_empty_pages")
                        break
                    continue
                consecutive_empty = 0
                log.info("ml_page", page=page_num, cards=len(cards))

                for card in cards:
                    raw = await self._extract_card(card)
                    if raw and raw.url not in seen_urls:
                        seen_urls.add(raw.url)
                        results.append(raw)

                await page.wait_for_timeout(int(settings.scrape_request_delay_sec * 1000))

        return results

    async def _load_with_retries(self, page, url: str, max_attempts: int = 3) -> list:
        for attempt in range(1, max_attempts + 1):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_selector("li.ui-search-layout__item", timeout=8_000)
                cards = await page.locator("li.ui-search-layout__item").all()
                if cards:
                    return cards
            except Exception as exc:
                log.debug("ml_attempt_failed", url=url, attempt=attempt, error=str(exc)[:80])
            await page.wait_for_timeout(2000 * attempt)
        return []

    async def _extract_card(self, card) -> RawProduct | None:
        try:
            link = card.locator(
                "a.poly-component__title, h3 a, a[class*='poly-component__title']"
            ).first
            title = (await link.inner_text()).strip()
            url = await link.get_attribute("href")
            if not title or not url:
                return None
            price_nodes = await card.locator(".andes-money-amount__fraction").all_inner_texts()
            if not price_nodes:
                return None
            price = _parse_clp(price_nodes[0])
            list_price = _parse_clp(price_nodes[1]) if len(price_nodes) > 1 else None
            m = re.search(r"MLC-?(\d+)", url)
            sku = m.group(0).replace("-", "") if m else None
            return RawProduct(
                retailer=self.retailer,
                retailer_sku=sku,
                url=url.split("#")[0],
                title=title,
                price_clp=price,
                list_price_clp=list_price if list_price and list_price > price else None,
                in_stock=True,
            )
        except Exception as exc:
            log.debug("ml_card_extract_failed", error=str(exc)[:100])
            return None


def _parse_clp(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


@click.command()
@click.option("--max-pages", type=int, default=None, help="Limit pages (smoke test).")
def main(max_pages: int | None) -> None:
    """Scrape MercadoLibre Chile categoría perfumes."""
    MercadoLibreScraper(max_pages=max_pages).run()


if __name__ == "__main__":
    main()
