"""Verifica URLs y marca listings muertos. Conservador y respetuoso.

Lecciones aprendidas:
1. Con 8 requests/segundo concurrentes contra el mismo dominio (Shopify, Ripley),
   los servidores devuelven 429 (Too Many Requests). El verificador antiguo
   marcaba esos como muertos = 70%+ falsos positivos.
2. Solo HTTP 404 es señal definitiva de "no existe". 410 también (Gone).
   Todo lo demás (429, 403, 500, timeouts) puede ser transitorio.

Por eso este verificador:
- Procesa **un dominio a la vez** (1 worker por dominio en paralelo entre dominios).
- Sleep configurable entre requests del mismo dominio (default 250ms).
- Marca muerto SOLO en HTTP 404 o 410 (después de retry).
- Cualquier otra cosa = vivo.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from urllib.parse import urlparse

import click
import structlog
from curl_cffi.requests import AsyncSession
from sqlalchemy import select, update

from scrapers.config import settings
from scrapers.db import session_scope
from scrapers.models import Listing

log = structlog.get_logger()

PER_DOMAIN_DELAY_SEC = 0.25
DEAD_STATUS_CODES = {404, 410}


def _domain_of(url: str) -> str:
    return urlparse(url).netloc.lower()


async def _verify_single(s: AsyncSession, url: str) -> bool:
    """True = vivo. False = muerto. Solo HTTP 404/410 cuenta como muerto."""
    for attempt in (1, 2):
        try:
            r = await s.get(url, allow_redirects=True)
        except Exception:
            if attempt == 2:
                return True  # transient — asumimos vivo
            await asyncio.sleep(1.0)
            continue
        if r.status_code in DEAD_STATUS_CODES:
            # Confirmar con segundo intento — algunos sites devuelven 404 transient
            if attempt == 1:
                await asyncio.sleep(1.0)
                continue
            return False
        return True
    return True


async def _process_domain(
    s: AsyncSession,
    rows: list[tuple[int, str, str]],
    stats: list[int],
    dead_ids: list[int],
    domain: str,
) -> None:
    """Procesa todas las URLs de un dominio secuencialmente con delay."""
    for lid, retailer, url in rows:
        alive = await _verify_single(s, url)
        if alive:
            stats[0] += 1
        else:
            stats[1] += 1
            dead_ids.append(lid)
        await asyncio.sleep(PER_DOMAIN_DELAY_SEC)


async def verify_all(only_retailer: str | None, limit: int | None) -> dict[str, tuple[int, int]]:
    with session_scope() as session:
        q = select(Listing.id, Listing.retailer, Listing.url).where(Listing.active.is_(True))
        if only_retailer:
            q = q.where(Listing.retailer == only_retailer)
        rows = session.execute(q).all()
    if limit:
        rows = rows[:limit]

    by_domain: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for row in rows:
        by_domain[_domain_of(row[2])].append(row)
    log.info("verify_start", total=len(rows), domains=len(by_domain))

    stats_per_retailer: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    dead_ids: list[int] = []

    async with AsyncSession(impersonate="chrome131", timeout=20) as s:
        s.headers.update({"accept-language": "es-CL,es;q=0.9"})

        async def domain_task(domain: str, rows: list[tuple[int, str, str]]):
            local_stats = [0, 0]
            local_dead: list[int] = []
            for lid, retailer, url in rows:
                alive = await _verify_single(s, url)
                if alive:
                    local_stats[0] += 1
                    stats_per_retailer[retailer][0] += 1
                else:
                    local_stats[1] += 1
                    stats_per_retailer[retailer][1] += 1
                    local_dead.append(lid)
                await asyncio.sleep(PER_DOMAIN_DELAY_SEC)
            dead_ids.extend(local_dead)
            log.info(
                "verify_domain_done",
                domain=domain,
                alive=local_stats[0],
                dead=local_stats[1],
            )

        await asyncio.gather(*[domain_task(d, r) for d, r in by_domain.items()])

    if dead_ids:
        with session_scope() as session:
            for i in range(0, len(dead_ids), 1000):
                chunk = dead_ids[i : i + 1000]
                session.execute(
                    update(Listing).where(Listing.id.in_(chunk)).values(active=False)
                )

    return {k: tuple(v) for k, v in stats_per_retailer.items()}


@click.command()
@click.option("--retailer", default=None, help="Solo verificar un retailer.")
@click.option("--limit", type=int, default=None, help="Tope de URLs (debugging).")
def main(retailer: str | None, limit: int | None) -> None:
    stats = asyncio.run(verify_all(retailer, limit))
    click.echo()
    click.echo("Resumen por retailer (vivos / muertos):")
    for r in sorted(stats):
        alive, dead = stats[r]
        pct = round(100 * dead / (alive + dead)) if (alive + dead) else 0
        click.echo(f"  {r:25}  ✅ {alive:5}  ❌ {dead:5}  ({pct}% muertos)")


if __name__ == "__main__":
    main()
