"""Scraper para paris.cl (Cencosud).

API interna descubierta vía DevTools:
  POST https://be-paris-backend-cl-ms-search.ccom.paris.cl/products/

Body: {filters, pagination: {page, pageSize}, term, ...}
Filter group_id=blzPerfumes devuelve ~12,341 productos (cat perfumes).

curl_cffi con impersonate=chrome131 pasa el WAF sin necesidad de browser.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

import click
import structlog
from curl_cffi import requests as cc_requests
from tenacity import retry, stop_after_attempt, wait_exponential

from scrapers.base import BaseScraper, RawProduct
from scrapers.config import settings

log = structlog.get_logger()

API_URL = "https://be-paris-backend-cl-ms-search.ccom.paris.cl/products/"
APP_ID = "34bb8686968a85a272a6c546ddcb9860db1ea14ee72f5207ef0c028280a6e7bc"
PAGE_SIZE = 30
GROUP_ID = "blzPerfumes"  # categoría Perfumes

HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "referer": "https://www.paris.cl/",
    "origin": "https://www.paris.cl",
    "accept-language": "es-CL",
}


class ParisScraper(BaseScraper):
    retailer = "paris"

    def __init__(self, max_pages: int | None = None) -> None:
        self.max_pages = max_pages

    def fetch_products(self) -> Iterable[RawProduct]:
        with cc_requests.Session(impersonate="chrome131") as s:
            s.headers.update(HEADERS)
            page = 1
            total: int | None = None
            while True:
                if self.max_pages and page > self.max_pages:
                    break
                data = self._fetch_page(s, page)
                results = data.get("results") or []
                if total is None:
                    total = data.get("total")
                    log.info("paris_total", total=total)
                if not results:
                    break
                log.info("paris_page", page=page, count=len(results), so_far=(page - 1) * PAGE_SIZE + len(results))
                for item in results:
                    raw = self._to_raw(item)
                    if raw:
                        yield raw
                if total and page * PAGE_SIZE >= total:
                    break
                page += 1
                time.sleep(settings.scrape_request_delay_sec)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
    def _fetch_page(self, s, page: int) -> dict:
        body = {
            "filters": [{"key": "group_id", "stringValues": [GROUP_ID]}],
            "pagination": {"page": page, "pageSize": PAGE_SIZE},
            "sortBy": "relevance",
            "serviceAbility": {
                "sameDayDelivery": False,
                "nextDayDelivery": False,
                "storePickUp": False,
            },
            "sponsoredProducts": False,  # evita duplicados que también vienen orgánicos
            "applicationId": APP_ID,
            "term": "",
        }
        r = s.post(API_URL, json=body, timeout=settings.scrape_timeout_sec)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _to_raw(item: dict) -> RawProduct | None:
        name = (item.get("name") or {}).get("es-CL")
        slug = (item.get("slug") or {}).get("es-CL")
        if not name or not slug:
            return None
        brand = item.get("brand")
        mv = item.get("masterVariant") or {}
        sku = mv.get("sku") or item.get("id")
        prices = mv.get("prices") or {}

        # Precio actual = offer si existe, sino regular
        current = _cent_amount(prices.get("offer")) or _cent_amount(prices.get("regular"))
        list_price = _cent_amount(prices.get("regular"))
        if current is None:
            return None
        if list_price and list_price <= current:
            list_price = None

        url = f"https://www.paris.cl/{slug}.html"
        return RawProduct(
            retailer="paris",
            retailer_sku=str(sku) if sku else None,
            url=url,
            title=name,
            price_clp=current,
            list_price_clp=list_price,
            in_stock=None,
            fallback_brand=brand,
        )


def _cent_amount(price_block: dict | None) -> int | None:
    if not price_block:
        return None
    value = price_block.get("value") or {}
    amt = value.get("centAmount")
    return int(amt) if amt is not None else None


@click.command()
@click.option("--max-pages", type=int, default=None, help="Limit pages (smoke test).")
def main(max_pages: int | None) -> None:
    """Scrape paris.cl perfumes category via internal API."""
    ParisScraper(max_pages=max_pages).run()


if __name__ == "__main__":
    main()
