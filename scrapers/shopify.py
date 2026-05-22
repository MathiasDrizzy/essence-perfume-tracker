"""Scraper genérico de tiendas Shopify usando el endpoint público /products.json.

Tiendas cubiertas:
- silkperfumes.cl
- productosdelujo.cl
- multimarcasperfumes.cl
- alishaperfumes.cl

El endpoint /products.json devuelve hasta 250 productos por página. Se pagina
hasta que una página viene vacía.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

import click
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from scrapers.base import BaseScraper, RawProduct
from scrapers.config import settings

log = structlog.get_logger()

SHOPIFY_SITES: dict[str, str] = {
    "silkperfumes": "https://silkperfumes.cl",
    "productosdelujo": "https://productosdelujo.cl",
    "multimarcasperfumes": "https://multimarcasperfumes.cl",
    "alishaperfumes": "https://alishaperfumes.cl",
    "eliteperfumes": "https://www.eliteperfumes.cl",
}


class ShopifyScraper(BaseScraper):
    def __init__(self, site_key: str, base_url: str) -> None:
        self.retailer = site_key
        self.base_url = base_url.rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
    def _fetch_page(self, client: httpx.Client, page: int) -> list[dict]:
        url = f"{self.base_url}/products.json"
        resp = client.get(url, params={"limit": 250, "page": page})
        resp.raise_for_status()
        return resp.json().get("products", [])

    def fetch_products(self) -> Iterable[RawProduct]:
        headers = {
            "User-Agent": settings.scrape_user_agent,
            "Accept": "application/json",
            "Accept-Language": "es-CL,es;q=0.9",
        }
        with httpx.Client(headers=headers, timeout=settings.scrape_timeout_sec) as client:
            page = 1
            while True:
                products = self._fetch_page(client, page)
                if not products:
                    break
                log.info("shopify_page", retailer=self.retailer, page=page, count=len(products))
                for p in products:
                    for variant in p.get("variants", []):
                        title = self._build_title(p, variant)
                        price = _to_int_clp(variant.get("price"))
                        list_price = _to_int_clp(variant.get("compare_at_price"))
                        if price is None:
                            continue
                        yield RawProduct(
                            retailer=self.retailer,
                            retailer_sku=str(variant.get("id")),
                            url=f"{self.base_url}/products/{p['handle']}?variant={variant['id']}",
                            title=title,
                            price_clp=price,
                            list_price_clp=list_price if list_price and list_price > price else None,
                            in_stock=variant.get("available"),
                            fallback_brand=p.get("vendor"),
                        )
                page += 1
                time.sleep(settings.scrape_request_delay_sec)

    @staticmethod
    def _build_title(product: dict, variant: dict) -> str:
        """Combina título del producto + título de la variante (excepto 'Default Title')."""
        base = product.get("title", "")
        vtitle = (variant.get("title") or "").strip()
        if vtitle and vtitle.lower() not in {"default title", "default"}:
            return f"{base} {vtitle}"
        return base


def _to_int_clp(value: str | int | float | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


@click.command()
@click.option(
    "--site",
    type=click.Choice([*SHOPIFY_SITES.keys(), "all"]),
    default="all",
    help="Shopify store to scrape (or 'all' for every configured store).",
)
def main(site: str) -> None:
    """Run the Shopify scraper for one or all configured stores."""
    targets = SHOPIFY_SITES if site == "all" else {site: SHOPIFY_SITES[site]}
    for key, url in targets.items():
        log.info("scraper_start", retailer=key)
        ShopifyScraper(key, url).run()


if __name__ == "__main__":
    main()
