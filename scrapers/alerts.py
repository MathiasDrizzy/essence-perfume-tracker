"""Telegram alerts: dispara mensaje cuando el precio mínimo de un perfume ≤ target.

Setup del usuario:
1. Hablar con @BotFather → /newbot → guardar token en TELEGRAM_BOT_TOKEN.
2. Hablar con el bot creado → /start (este módulo responde con tu chat_id).
3. Crear alertas en el dashboard usando ese chat_id.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import click
import structlog
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes

from scrapers.config import settings
from scrapers.db import session_scope
from scrapers.models import Alert, Listing, Perfume, PriceHistory

log = structlog.get_logger()


def _min_price_for_perfume(session: Session, perfume_id: int) -> tuple[int, str, str] | None:
    """Devuelve (min_price_clp, retailer, listing_url) más reciente entre todos los listings."""
    rows = session.execute(
        select(
            PriceHistory.price_clp,
            Listing.retailer,
            Listing.url,
        )
        .join(Listing, Listing.id == PriceHistory.listing_id)
        .where(Listing.perfume_id == perfume_id, Listing.active.is_(True))
        .order_by(desc(PriceHistory.scraped_at))
        .limit(50)
    ).all()
    if not rows:
        return None
    # rows ya están ordenadas por scraped_at desc; tomamos solo el último precio
    # por retailer y luego buscamos el mínimo
    latest_per_retailer: dict[str, tuple[int, str]] = {}
    for price, retailer, url in rows:
        if retailer not in latest_per_retailer:
            latest_per_retailer[retailer] = (price, url)
    if not latest_per_retailer:
        return None
    retailer, (price, url) = min(latest_per_retailer.items(), key=lambda x: x[1][0])
    return price, retailer, url


async def check_and_send_alerts() -> int:
    """Recorre alertas activas, manda Telegram si se cumple target. Devuelve # disparadas."""
    if not settings.telegram_bot_token:
        log.warning("alerts_no_token", message="TELEGRAM_BOT_TOKEN missing — skipping alerts")
        return 0

    bot = Bot(token=settings.telegram_bot_token)
    triggered = 0
    with session_scope() as session:
        alerts = session.execute(select(Alert).where(Alert.active.is_(True))).scalars().all()
        for alert in alerts:
            result = _min_price_for_perfume(session, alert.perfume_id)
            if not result:
                continue
            current_min, retailer, url = result
            if current_min > alert.target_price_clp:
                continue
            perfume = session.get(Perfume, alert.perfume_id)
            if perfume is None:
                continue
            text = (
                f"🎯 *Alerta de precio*\n\n"
                f"*{perfume.brand} {perfume.name}*\n"
                f"{perfume.volume_ml} ml"
                f"{' ' + perfume.concentration if perfume.concentration else ''}\n\n"
                f"Precio actual mínimo: *${current_min:,}* en _{retailer}_\n"
                f"Tu objetivo: ${alert.target_price_clp:,}\n\n"
                f"[Ir al producto]({url})"
            )
            try:
                await bot.send_message(
                    chat_id=alert.telegram_chat_id,
                    text=text,
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
                alert.triggered_at = datetime.now(UTC)
                triggered += 1
                log.info("alert_triggered", perfume_id=alert.perfume_id, price=current_min, target=alert.target_price_clp)
            except Exception as exc:
                log.warning("alert_send_failed", alert_id=alert.id, error=str(exc)[:200])
    return triggered


# Bot interactivo: comando /start devuelve el chat_id
async def _start_cmd(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    msg = (
        f"¡Hola! Soy tu bot de alertas de perfumes.\n\n"
        f"Tu chat_id es: `{chat_id}`\n\n"
        f"Pégalo en el dashboard al crear alertas y te avisaré "
        f"cuando un perfume baje al precio objetivo."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


@click.group()
def cli() -> None:
    pass


@cli.command()
def check() -> None:
    """Corre el chequeo de alertas (típicamente desde el orchestrator después del scrape)."""
    n = asyncio.run(check_and_send_alerts())
    click.echo(f"Alerts triggered: {n}")


@cli.command()
def bot() -> None:
    """Corre el bot en modo interactivo: responde /start con el chat_id."""
    if not settings.telegram_bot_token:
        click.echo("ERROR: TELEGRAM_BOT_TOKEN missing in .env", err=True)
        raise click.Abort()
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", _start_cmd))
    click.echo("Bot listening for /start... press Ctrl+C to stop")
    app.run_polling()


if __name__ == "__main__":
    cli()
