"""Scraper para simple.ripley.cl.

Estrategia: parsear el DOM con selectolax y extraer **la URL real** de cada
card en lugar de construirla. Antes construíamos `{slug}-{sku}p`, lo que
fallaba para productos marketplace (URLs tipo `-mpmXXXXXXX`).

Ripley no bloquea curl_cffi con impersonate=chrome131. Paginación: `?page=N`.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from math import ceil

import click
import structlog
from curl_cffi import requests as cc_requests
from selectolax.parser import HTMLParser
from tenacity import retry, stop_after_attempt, wait_exponential

from scrapers.base import BaseScraper, RawProduct
from scrapers.config import settings

log = structlog.get_logger()

CATEGORY_URL = "https://simple.ripley.cl/belleza/perfumeria"
PAGE_SIZE = 48
BASE_URL = "https://simple.ripley.cl"

# href de producto Ripley: termina en `-{digits}p` (catálogo) o `-mpm{digits}` (marketplace)
PRODUCT_HREF_RE = re.compile(r"-(?:\d{6,}p|mpm\d+)$")
PRICE_RE = re.compile(r"\$\s*([\d.]+)")
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


class RipleyScraper(BaseScraper):
    retailer = "ripley"

    def __init__(self, max_pages: int | None = None) -> None:
        self.max_pages = max_pages

    def fetch_products(self) -> Iterable[RawProduct]:
        seen_urls: set[str] = set()
        with cc_requests.Session(impersonate="chrome131") as s:
            s.headers.update({"accept-language": "es-CL,es;q=0.9"})

            # Primera página: necesitamos total + extracción
            html = self._fetch_html(s, 1)
            total = self._extract_total(html)
            total_pages = ceil(total / PAGE_SIZE) if total else 1
            if self.max_pages:
                total_pages = min(total_pages, self.max_pages)
            log.info("ripley_start", total=total, pages=total_pages)

            empties = 0
            for page in range(1, total_pages + 1):
                if page > 1:
                    try:
                        html = self._fetch_html(s, page)
                    except Exception as exc:
                        log.warning("ripley_fetch_failed", page=page, error=str(exc)[:200])
                        empties += 1
                        if empties >= 3:
                            break
                        time.sleep(settings.scrape_request_delay_sec * 2)
                        continue

                cards = list(self._extract_cards(html))
                if not cards:
                    empties += 1
                    log.warning("ripley_no_cards", page=page, consecutive=empties)
                    if empties >= 3:
                        break
                    continue
                empties = 0

                new = 0
                for card in cards:
                    url = card["url"]
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    raw = self._card_to_raw(card)
                    if raw:
                        new += 1
                        yield raw
                log.info("ripley_page", page=page, batch=len(cards), new=new, kept=len(seen_urls))
                time.sleep(settings.scrape_request_delay_sec)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
    def _fetch_html(self, s, page: int) -> str:
        url = f"{CATEGORY_URL}?page={page}"
        r = s.get(url, timeout=settings.scrape_timeout_sec)
        r.raise_for_status()
        return r.text

    @staticmethod
    def _extract_total(html: str) -> int:
        """Extrae el total desde __NEXT_DATA__ (sigue siendo la fuente más confiable)."""
        m = NEXT_DATA_RE.search(html)
        if not m:
            return 0
        import json
        try:
            data = json.loads(m.group(1))
            return int(
                data["props"]["pageProps"]["findabilityProps"]["data"].get("total", 0)
            )
        except (KeyError, TypeError, ValueError):
            return 0

    @staticmethod
    def _extract_cards(html: str):
        """Yieldea dicts {url, title, price, list_price} desde el DOM."""
        tree = HTMLParser(html)
        for a in tree.css("a"):
            href = (a.attributes.get("href") or "").strip()
            if not href.startswith("/"):
                continue
            href_clean = href.split("?")[0]
            if not PRODUCT_HREF_RE.search(href_clean):
                continue
            img = a.css_first("img")
            if img is None:
                continue
            title = (img.attributes.get("alt") or "").strip()
            if not title or len(title) < 5:
                continue

            # Precios: hay typicamente 2-3 valores. El primero es el actual,
            # el más alto en la cadena ($147.990 / $77.990 ripleyPrice).
            text = a.text(separator=" ", strip=True)
            prices = [
                int(p.replace(".", "")) for p in PRICE_RE.findall(text) if p
            ]
            if not prices:
                continue
            # Heurística: el precio "actual" es el segundo si hay 3 (precio normal tachado,
            # precio actual, precio Ripley card); el primero si hay 2 (actual + tachado).
            if len(prices) >= 3:
                current = prices[1]
                list_price = prices[0]
            elif len(prices) == 2:
                # Si el primero > segundo, el primero es el tachado y el segundo el actual.
                if prices[0] > prices[1]:
                    list_price, current = prices[0], prices[1]
                else:
                    current, list_price = prices[0], prices[1]
            else:
                current = prices[0]
                list_price = None

            yield {
                "url": BASE_URL + href_clean,
                "title": title,
                "price": current,
                "list_price": list_price if list_price and list_price > current else None,
            }

    @staticmethod
    def _card_to_raw(card: dict) -> RawProduct | None:
        # Intenta extraer marca del comienzo del título (mayúsculas seguidas)
        title = card["title"]
        brand_match = re.match(r"^(?:PERFUME\s+(?:MUJER\s+|HOMBRE\s+|UNISEX\s+)?)?([A-Z][A-Z &]+?)(?:\s+[A-Z]?[a-z])", title)
        fallback_brand = brand_match.group(1).strip().title() if brand_match else None

        # SKU = última parte numérica del href
        url_path = card["url"].rsplit("/", 1)[-1]
        sku_m = re.search(r"-(\d{6,})p$|-mpm(\d+)$", url_path)
        sku = (sku_m.group(1) or sku_m.group(2)) if sku_m else None

        return RawProduct(
            retailer="ripley",
            retailer_sku=sku,
            url=card["url"],
            title=title,
            price_clp=card["price"],
            list_price_clp=card["list_price"],
            in_stock=None,
            fallback_brand=fallback_brand,
        )


@click.command()
@click.option("--max-pages", type=int, default=None, help="Limit pages (smoke test).")
def main(max_pages: int | None) -> None:
    """Scrape simple.ripley.cl perfumes parsing real DOM hrefs."""
    RipleyScraper(max_pages=max_pages).run()


if __name__ == "__main__":
    main()
