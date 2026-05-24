"""Scraper para falabella.com/falabella-cl.

Falabella supuestamente usa DataDome pero curl_cffi con impersonate=chrome131
pasa el WAF y obtiene SSR HTML con __NEXT_DATA__ que embed la lista de productos.

Estrategia: search URL `?Ntt=perfume&page=N` ~10k resultados / 48 por página.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from math import ceil

import click
import structlog
from curl_cffi import requests as cc_requests
from tenacity import retry, stop_after_attempt, wait_exponential

from scrapers.base import BaseScraper, RawProduct
from scrapers.config import settings

log = structlog.get_logger()

SEARCH_URL = "https://www.falabella.com/falabella-cl/search"
SEARCH_TERM = "perfume"
PAGE_SIZE = 48
# Páginas a fetchear en paralelo. Antes secuencial: 210 pages × ~9s = 33 min.
# Con 4 paralelas: ~210/4 × 9s = ~8 min.
PAGE_BATCH = 8

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


class FalabellaScraper(BaseScraper):
    retailer = "falabella"

    def __init__(self, max_pages: int | None = None) -> None:
        self.max_pages = max_pages

    def fetch_products(self) -> Iterable[RawProduct]:
        seen_ids: set[str] = set()
        with cc_requests.Session(impersonate="chrome131") as s:
            s.headers.update({"accept-language": "es-CL,es;q=0.9"})

            # Fetch página 1 sincrónico para obtener total y los primeros productos
            data1 = self._fetch_page(s, 1)
            pp = data1["props"]["pageProps"]
            total = pp.get("pagination", {}).get("count", 0)
            total_pages = ceil(total / PAGE_SIZE) if total else 1
            if self.max_pages:
                total_pages = min(total_pages, self.max_pages)
            log.info("falabella_start", total=total, pages=total_pages)

            # Procesar primera página
            for raw in self._yield_results(data1, seen_ids, 1):
                yield raw

            # Fetch páginas 2..total_pages en batches de PAGE_BATCH paralelos.
            with ThreadPoolExecutor(max_workers=PAGE_BATCH) as ex:
                page = 2
                while page <= total_pages:
                    pages_in_batch = list(range(page, min(page + PAGE_BATCH, total_pages + 1)))
                    futures = {ex.submit(self._fetch_page, s, p): p for p in pages_in_batch}
                    by_page: dict[int, dict] = {}
                    for fut in futures:
                        p_num = futures[fut]
                        try:
                            by_page[p_num] = fut.result()
                        except Exception as exc:
                            log.warning("falabella_page_failed", page=p_num, error=str(exc)[:150])
                            by_page[p_num] = {}
                    for p_num in pages_in_batch:
                        for raw in self._yield_results(by_page.get(p_num) or {}, seen_ids, p_num):
                            yield raw
                    page += PAGE_BATCH
                    time.sleep(min(settings.scrape_request_delay_sec, 0.5))

    def _yield_results(self, data: dict, seen_ids: set, page_num: int) -> Iterable[RawProduct]:
        results = (data.get("props") or {}).get("pageProps", {}).get("results") or []
        new = 0
        for p in results:
            pid = str(p.get("productId") or "")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            raw = self._to_raw(p)
            if raw:
                new += 1
                yield raw
        log.info("falabella_page", page=page_num, batch=len(results), new=new, kept=len(seen_ids))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
    def _fetch_page(self, s, page: int) -> dict:
        params = {"Ntt": SEARCH_TERM, "page": page}
        r = s.get(SEARCH_URL, params=params, timeout=settings.scrape_timeout_sec)
        r.raise_for_status()
        m = NEXT_DATA_RE.search(r.text)
        if not m:
            raise ValueError(f"__NEXT_DATA__ not found on page {page}")
        return json.loads(m.group(1))

    @staticmethod
    def _to_raw(p: dict) -> RawProduct | None:
        name = p.get("displayName")
        url = p.get("url")
        if not name or not url:
            return None

        # prices es lista de blocks; encontrar precio actual y precio "antes"
        current: int | None = None
        list_price: int | None = None
        for block in p.get("prices") or []:
            ptype = block.get("type", "")
            crossed = block.get("crossed", False)
            value = _parse_clp(block.get("price"))
            if value is None:
                continue
            if crossed or ptype == "normalPrice":
                if list_price is None or value > list_price:
                    list_price = value
            else:
                if current is None:
                    current = value

        if current is None:
            return None
        if list_price and list_price <= current:
            list_price = None

        return RawProduct(
            retailer="falabella",
            retailer_sku=str(p.get("productId") or p.get("skuId") or ""),
            url=url,
            title=name,
            price_clp=current,
            list_price_clp=list_price,
            in_stock=(p.get("availability") or {}).get("isInStock"),
            fallback_brand=p.get("brand"),
        )


def _parse_clp(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        value = value[0]
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


@click.command()
@click.option("--max-pages", type=int, default=None, help="Limit pages (smoke test).")
def main(max_pages: int | None) -> None:
    """Scrape falabella.com search results for perfume."""
    FalabellaScraper(max_pages=max_pages).run()


if __name__ == "__main__":
    main()
