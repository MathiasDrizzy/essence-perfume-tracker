"""Scraper para sairam.cl (Jumpseller).

Estrategia:
1. Descargar sitemap.xml.
2. Filtrar URLs de productos (path /es/perfume-*, /es/body-mist-*, etc.).
3. Para cada URL, fetch concurrente con curl_cffi (impersonate Chrome).
4. Extraer name/brand/sku desde JSON-LD y precio desde og:price meta.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable

import click
import structlog
from curl_cffi.requests import AsyncSession

from scrapers.base import BaseScraper, RawProduct
from scrapers.config import settings

log = structlog.get_logger()

SITEMAP_URL = "https://sairam.cl/sitemap.xml"
SITE_BASE = "https://sairam.cl"
CONCURRENCY = 6  # respeta al servidor

# Path prefixes que indican producto (encontrados al inspeccionar el sitemap)
PRODUCT_PREFIXES = ("/es/perfume-", "/es/body-mist-", "/es/desodorante-", "/es/loción-", "/es/locion-")


class JumpsellerScraper(BaseScraper):
    retailer = "sairam"

    def __init__(self, limit: int | None = None) -> None:
        self.limit = limit

    def fetch_products(self) -> Iterable[RawProduct]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[RawProduct]:
        urls = self._product_urls_from_sitemap()
        if self.limit:
            urls = urls[: self.limit]
        log.info("sairam_sitemap", total_product_urls=len(urls))

        results: list[RawProduct] = []
        sem = asyncio.Semaphore(CONCURRENCY)
        async with AsyncSession(impersonate="chrome131", timeout=settings.scrape_timeout_sec) as s:
            tasks = [self._fetch_one(s, sem, url) for url in urls]
            for i, fut in enumerate(asyncio.as_completed(tasks), start=1):
                raw = await fut
                if raw:
                    results.append(raw)
                if i % 200 == 0:
                    log.info("sairam_progress", done=i, total=len(urls), kept=len(results))
        return results

    def _product_urls_from_sitemap(self) -> list[str]:
        # Síncrono — sólo se llama una vez
        from curl_cffi import requests
        r = requests.get(SITEMAP_URL, impersonate="chrome131", timeout=20)
        r.raise_for_status()
        urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
        return [u for u in urls if any(u.startswith(SITE_BASE + p) for p in PRODUCT_PREFIXES)]

    async def _fetch_one(self, s: AsyncSession, sem: asyncio.Semaphore, url: str) -> RawProduct | None:
        async with sem:
            try:
                r = await s.get(url)
                if r.status_code != 200:
                    return None
                html = r.text
            except Exception as exc:
                log.debug("sairam_fetch_failed", url=url, error=str(exc)[:80])
                return None

        title, brand, sku = _parse_jsonld(html)
        price = _parse_og_price(html)
        list_price = _parse_list_price(html, current=price)

        if not title or price is None:
            return None

        return RawProduct(
            retailer=self.retailer,
            retailer_sku=sku,
            url=url,
            title=title,
            price_clp=price,
            list_price_clp=list_price if list_price and list_price > price else None,
            in_stock=None,
            fallback_brand=brand,
        )


def _parse_jsonld(html: str) -> tuple[str | None, str | None, str | None]:
    """Devuelve (name, brand, sku) extraídos del primer bloque JSON-LD Product."""
    for blob in re.findall(r"<script[^>]+ld\+json[^>]*>(.*?)</script>", html, re.DOTALL):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product":
                brand_field = item.get("brand")
                brand = brand_field.get("name") if isinstance(brand_field, dict) else brand_field
                return item.get("name"), brand, str(item.get("sku") or "") or None
    return None, None, None


def _parse_og_price(html: str) -> int | None:
    m = re.search(
        r'<meta[^>]*property="product:price:amount"[^>]*content="([^"]+)"',
        html,
    )
    if not m:
        return None
    try:
        return int(float(m.group(1)))
    except (TypeError, ValueError):
        return None


def _parse_list_price(html: str, current: int | None) -> int | None:
    """list_price = el precio anterior tachado (compare_at). Heurística: el segundo
    valor numérico de las ofertas suele ser el precio original."""
    if current is None:
        return None
    prices = re.findall(r'"price"\s*:\s*"?([\d.]+)"?', html)
    candidates = []
    for p in prices:
        try:
            v = int(float(p))
            if v > current:
                candidates.append(v)
        except (TypeError, ValueError):
            continue
    return max(candidates) if candidates else None


@click.command()
@click.option("--limit", type=int, default=None, help="Limit number of products (smoke testing).")
def main(limit: int | None) -> None:
    """Scrape sairam.cl (Jumpseller)."""
    JumpsellerScraper(limit=limit).run()


if __name__ == "__main__":
    main()
