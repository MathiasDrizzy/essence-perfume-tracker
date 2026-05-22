"""Scraper para MercadoLibre Chile.

La API pública (api.mercadolibre.com) ahora exige auth para búsquedas;
y curl_cffi es bloqueado por su WAF. Estrategia: Playwright + stealth contra
la categoría de fragancias paginada.

ML cachea hasta ~2000 resultados por categoría sin filtros (40 páginas × 50).
Para mayor cobertura, podemos extender en el futuro iterando por marca.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable

import click
import structlog
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from scrapers.base import BaseScraper, RawProduct
from scrapers.config import settings

log = structlog.get_logger()

BASE_URL = "https://listado.mercadolibre.cl/perfume"
PAGE_SIZE = 50
MAX_PAGES = 40  # ~2000 productos


class MercadoLibreScraper(BaseScraper):
    retailer = "mercadolibre"

    def fetch_products(self) -> Iterable[RawProduct]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[RawProduct]:
        results: list[RawProduct] = []
        seen_urls: set[str] = set()
        async with Stealth().use_async(async_playwright()) as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=settings.scrape_user_agent,
                locale="es-CL",
                viewport={"width": 1280, "height": 900},
            )
            page = await ctx.new_page()
            consecutive_empty = 0
            for page_num in range(1, MAX_PAGES + 1):
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

            await browser.close()
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
            # Título y URL
            link = card.locator("a.poly-component__title, h3 a, a[class*='poly-component__title']").first
            title = (await link.inner_text()).strip()
            url = await link.get_attribute("href")
            if not title or not url:
                return None

            # Precio: el span ".andes-money-amount__fraction" suele tener el primer precio (actual)
            price_nodes = await card.locator(".andes-money-amount__fraction").all_inner_texts()
            if not price_nodes:
                return None
            price = _parse_clp(price_nodes[0])
            list_price = _parse_clp(price_nodes[1]) if len(price_nodes) > 1 else None

            # SKU = MLC item id desde la URL
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
def main() -> None:
    """Scrape MercadoLibre Chile categoría perfumes."""
    MercadoLibreScraper().run()


if __name__ == "__main__":
    main()
