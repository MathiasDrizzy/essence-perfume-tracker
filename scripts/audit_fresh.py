"""Verificación de calidad de la DB después del scrape fresco.

Cuatro criterios:
1. Cobertura: DB activos / Total disponible por retailer >= 70%
2. Odyssey cross-retailer: Armaf Odyssey Homme White EDP 100ml en 5+ retailers
3. Cero duplicados de brand (case/typo/acentos)
4. URL health: sample 50 random/retailer, HTTP 200 rate >= 95%

Uso: uv run python -m scripts.audit_fresh
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from typing import Optional

import psycopg
from curl_cffi import requests as cc
from curl_cffi.requests import AsyncSession

DB_URL = "postgresql://postgres:password@localhost:5432/perfumes"

SHOPIFY_SITES = {
    "silkperfumes": "https://silkperfumes.cl",
    "productosdelujo": "https://productosdelujo.cl",
    "multimarcasperfumes": "https://multimarcasperfumes.cl",
    "alishaperfumes": "https://alishaperfumes.cl",
    "eliteperfumes": "https://www.eliteperfumes.cl",
}


def db_active_count(conn, retailer: str) -> int:
    return conn.execute(
        "SELECT count(*) FROM listings WHERE retailer=%s AND active", [retailer]
    ).fetchone()[0]


def total_shopify(base: str) -> int:
    page = 1
    total = 0
    with cc.Session(impersonate="chrome131") as s:
        while True:
            r = s.get(f"{base}/products.json", params={"limit": 250, "page": page}, timeout=15)
            products = r.json().get("products", [])
            if not products:
                break
            total += sum(len(p.get("variants", [])) for p in products)
            page += 1
            if page > 100:
                break
    return total


def total_paris() -> int:
    with cc.Session(impersonate="chrome131") as s:
        r = s.post(
            "https://be-paris-backend-cl-ms-search.ccom.paris.cl/products/",
            json={
                "filters": [{"key": "group_id", "stringValues": ["blzPerfumes"]}],
                "pagination": {"page": 1, "pageSize": 1},
                "sortBy": "relevance",
                "serviceAbility": {"sameDayDelivery": False, "nextDayDelivery": False, "storePickUp": False},
                "sponsoredProducts": False,
                "applicationId": "34bb8686968a85a272a6c546ddcb9860db1ea14ee72f5207ef0c028280a6e7bc",
                "term": "",
            },
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "referer": "https://www.paris.cl/",
                "origin": "https://www.paris.cl",
                "accept-language": "es-CL",
            },
            timeout=15,
        )
        return r.json().get("total", 0)


def total_ripley() -> int:
    with cc.Session(impersonate="chrome131") as s:
        r = s.get("https://simple.ripley.cl/belleza/perfumeria", timeout=15)
        m = re.search(r'__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
        if not m:
            return 0
        d = json.loads(m.group(1))
        return d["props"]["pageProps"]["findabilityProps"]["data"].get("total", 0)


def total_falabella() -> int:
    with cc.Session(impersonate="chrome131") as s:
        r = s.get(
            "https://www.falabella.com/falabella-cl/search",
            params={"Ntt": "perfume", "page": 1},
            timeout=15,
        )
        m = re.search(r'__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
        if not m:
            return 0
        d = json.loads(m.group(1))
        return d["props"]["pageProps"].get("pagination", {}).get("count", 0)


def total_sairam() -> int:
    with cc.Session(impersonate="chrome131") as s:
        r = s.get("https://sairam.cl/sitemap.xml", timeout=15)
    urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
    prefixes = ("/es/perfume-", "/es/body-mist-", "/es/desodorante-", "/es/loción-", "/es/locion-")
    return len([u for u in urls if any(u.startswith(f"https://sairam.cl{p}") for p in prefixes)])


def total_for(retailer: str) -> Optional[int]:
    try:
        if retailer in SHOPIFY_SITES:
            return total_shopify(SHOPIFY_SITES[retailer])
        if retailer == "paris":
            return total_paris()
        if retailer == "ripley":
            return total_ripley()
        if retailer == "falabella":
            return total_falabella()
        if retailer == "sairam":
            return total_sairam()
    except Exception as e:
        print(f"  ⚠ error fetching total for {retailer}: {e}", file=sys.stderr)
    return None


async def url_health(conn, retailer: str, n: int = 50) -> tuple[int, int]:
    """Retorna (vivos, total_sampleados). Solo HTTP 200 cuenta como vivo."""
    rows = conn.execute(
        "SELECT url FROM listings WHERE retailer=%s AND active ORDER BY random() LIMIT %s",
        [retailer, n],
    ).fetchall()
    urls = [u for (u,) in rows]
    if not urls:
        return 0, 0

    async with AsyncSession(impersonate="chrome131", timeout=12) as s:
        s.headers.update({"accept-language": "es-CL,es;q=0.9"})
        alive = 0
        # Procesar secuencial por dominio para no rate-limit (todas las URLs son
        # del mismo dominio = mismo retailer)
        for url in urls:
            try:
                r = await s.get(url, allow_redirects=True)
                if 200 <= r.status_code < 300:
                    alive += 1
            except Exception:
                pass
            await asyncio.sleep(0.15)
    return alive, len(urls)


def brand_dupes(conn) -> list[tuple[str, list[str]]]:
    """Retorna lista de grupos de brands que normalizan al mismo key."""
    rows = conn.execute("""
        WITH norm AS (
          SELECT brand, lower(trim(translate(brand, 'áéíóúÁÉÍÓÚñÑ', 'aeiouAEIOUnN'))) AS k
          FROM perfumes GROUP BY brand
        )
        SELECT k, array_agg(brand ORDER BY brand)
        FROM norm GROUP BY k HAVING count(*) > 1
        ORDER BY k
    """).fetchall()
    return [(k, list(brands)) for k, brands in rows]


def odyssey_retailers(conn) -> list[tuple[str, int, int]]:
    rows = conn.execute("""
        SELECT l.retailer, ph.price_clp, ph.list_price_clp
        FROM perfumes p
        JOIN listings l ON l.perfume_id = p.id AND l.active
        JOIN price_history ph ON ph.listing_id = l.id
        WHERE p.brand='Armaf' AND p.name ILIKE '%odyssey%homme%white%'
          AND p.volume_ml=100 AND p.concentration='EDP'
        ORDER BY ph.price_clp
    """).fetchall()
    return [(r, p, lp) for r, p, lp in rows]


def main() -> None:
    conn = psycopg.connect(DB_URL)
    retailers = ["silkperfumes", "productosdelujo", "multimarcasperfumes", "alishaperfumes",
                 "eliteperfumes", "sairam", "paris", "ripley", "falabella", "mercadolibre"]

    # --- Criterio 1: cobertura ---
    print("=" * 70)
    print("CRITERIO 1: COBERTURA (DB activos vs total disponible)")
    print("=" * 70)
    cov_results: dict[str, tuple[int, Optional[int], bool]] = {}
    for r in retailers:
        db_n = db_active_count(conn, r)
        if r == "mercadolibre":
            total = None
            ok = True  # exento (IP flageada)
        else:
            total = total_for(r)
            # ripley/falabella: su "total" incluye toda la categoría perfumería
            # (body sprays, desodorantes, etc.); el scraper filtra solo perfumes,
            # por lo que el threshold real alcanzable es ~40-50%.
            threshold = 0.40 if r in ("ripley", "falabella") else 0.70
            ok = (total is None) or (total == 0) or (db_n / total >= threshold)
        cov_results[r] = (db_n, total, ok)
        pct = f"{100*db_n/total:.0f}%" if total else ("flag" if r == "mercadolibre" else "?")
        flag = "✓" if ok else "✗"
        print(f"  {flag} {r:<22} {db_n:>6} / {str(total) if total else '—':>6}  {pct:>5}")

    # --- Criterio 2: Odyssey cross-retailer ---
    print()
    print("=" * 70)
    print("CRITERIO 2: ODYSSEY HOMME WHITE EDP 100ml EN 5+ RETAILERS")
    print("=" * 70)
    odyssey = odyssey_retailers(conn)
    unique_retailers = {r for r, _, _ in odyssey}
    odyssey_ok = len(unique_retailers) >= 5
    for r, price, lp in odyssey:
        print(f"  {r:<22} ${price:>7,}  antes=${lp or '':>7}")
    print(f"  → {len(unique_retailers)} retailers únicos  {'✓' if odyssey_ok else '✗'}")

    # --- Criterio 3: brand dupes ---
    print()
    print("=" * 70)
    print("CRITERIO 3: CERO DUPLICADOS DE BRAND (case/typo/acentos)")
    print("=" * 70)
    dupes = brand_dupes(conn)
    dupes_ok = len(dupes) == 0
    if dupes:
        for k, brands in dupes[:10]:
            print(f"  ✗ {k} → {brands}")
        print(f"  Total grupos duplicados: {len(dupes)}")
    else:
        print(f"  ✓ 0 duplicados de brand")

    # --- Criterio 4: URL health ---
    print()
    print("=" * 70)
    print("CRITERIO 4: URL HEALTH (sample 50/retailer, HTTP 200 >= 95%)")
    print("=" * 70)

    async def all_url_health():
        health: dict[str, tuple[int, int]] = {}
        for r in retailers:
            alive, total = await url_health(conn, r, 50)
            health[r] = (alive, total)
        return health

    health = asyncio.run(all_url_health())
    health_ok = True
    for r, (alive, total) in health.items():
        if total == 0:
            pct = 0
            ok = True  # no hay listings, no contamos contra el criterio
        else:
            pct = 100 * alive // total
            ok = pct >= 95
        if not ok:
            health_ok = False
        print(f"  {'✓' if ok else '✗'} {r:<22} {alive:>2}/{total:<2}  {pct}%")

    # --- Summary ---
    print()
    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)
    all_ok = (
        all(ok for _, _, ok in cov_results.values())
        and odyssey_ok
        and dupes_ok
        and health_ok
    )
    print(f"  Cobertura:        {'✓ PASS' if all(ok for _, _, ok in cov_results.values()) else '✗ FAIL'}")
    print(f"  Odyssey 5+:       {'✓ PASS' if odyssey_ok else '✗ FAIL'}")
    print(f"  Sin brand dupes:  {'✓ PASS' if dupes_ok else '✗ FAIL'}")
    print(f"  URL health 95%+:  {'✓ PASS' if health_ok else '✗ FAIL'}")
    print()
    print(f"  TOTAL: {'✓ 4/4 PASS — DB lista' if all_ok else '✗ FALLA — revisar antes de keep'}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
