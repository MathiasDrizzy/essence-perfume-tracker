# ESSENCE — Catálogo de Perfumería Chilena

> Comparador histórico de precios de perfumes en **10 tiendas chilenas** con dashboard editorial y alertas Telegram.

![Stack](https://img.shields.io/badge/python-3.12+-blue) ![Next.js](https://img.shields.io/badge/next.js-16-black) ![License](https://img.shields.io/badge/license-MIT-green)

Cada noche un cron en GitHub Actions raspa las 10 tiendas, normaliza y unifica los mismos perfumes entre vendedores, guarda el histórico en Postgres y notifica por Telegram si un perfume baja al precio objetivo.

## 🪞 Tiendas cubiertas

| Tienda | Plataforma | Productos | Estrategia |
|---|---|---:|---|
| productosdelujo.cl | Shopify | 10.500 | `/products.json` |
| paris.cl | Cencosud | 9.700 | API JSON interna (POST) |
| falabella.com/cl | Falabella | 6.700 | `__NEXT_DATA__` SSR |
| multimarcasperfumes.cl | Shopify | 5.100 | `/products.json` |
| sairam.cl | Jumpseller | 4.100 | sitemap + curl_cffi |
| silkperfumes.cl | Shopify | 4.000 | `/products.json` |
| alishaperfumes.cl | Shopify | 3.400 | `/products.json` |
| ripley.cl | Ripley | 3.300 | DOM parse (selectolax) |
| eliteperfumes.cl | Shopify | 1.600 | `/products.json` |
| mercadolibre.cl | ML | 280 | Playwright + stealth |

**Total ~49.700 listings activos, 0–2% URLs muertas** (verificado per-dominio, sin rate-limit).

## 🛠 Stack

- **Scraping** — Python 3.12 · `httpx` · `curl_cffi` (impersonate Chrome) · `selectolax` · Playwright + stealth · `tenacity`
- **DB** — Postgres 16 (local Docker o Supabase) · SQLAlchemy 2 · Alembic
- **Dashboard** — Next.js 16 (App Router) · TypeScript · Tailwind 3 · Recharts · `postgres-js`
- **Cron** — GitHub Actions diario 04:00 CLT
- **Alertas** — `python-telegram-bot`

## 🚀 Setup local

### 1. Prerequisitos (Mac)

```bash
brew install uv node pnpm
# Docker Desktop instalado y corriendo
```

### 2. Backend

```bash
# Postgres local
docker compose up -d

# Deps Python
uv sync

# Variables de entorno
cp .env.example .env
# Editar TELEGRAM_BOT_TOKEN si vas a usar alertas

# Schema
uv run alembic upgrade head

# Chromium para MercadoLibre (~100 MB)
uv run playwright install chromium

# Camoufox para Falabella (opcional, ya no se usa con curl_cffi)
# uv run camoufox fetch
```

### 3. Correr scrapers

```bash
# Todos en paralelo (5 workers)
uv run python -m scrapers.run_all

# Uno solo
uv run python -m scrapers.run_all --only paris

# Smoke test rápido
uv run python -m scrapers.shopify --site silkperfumes
uv run python -m scrapers.paris --max-pages 3
uv run python -m scrapers.ripley --max-pages 3
uv run python -m scrapers.falabella --max-pages 3

# Verificar URLs vivas (limpia muertas)
uv run python -m scrapers.verify_urls
```

### 4. Dashboard

```bash
cd dashboard
cp .env.local.example .env.local
pnpm install
pnpm dev          # http://localhost:3000
```

### 5. Telegram bot (opcional)

```bash
# 1. @BotFather → /newbot → guarda el token en .env
# 2. uv run python -m scrapers.alerts bot
# 3. Habla con tu bot → /start → te devuelve tu chat_id
# 4. Usa ese chat_id en el dashboard al crear alertas
```

## ☁️ Deploy gratis

### Supabase (Postgres)

1. Crea proyecto en [supabase.com](https://supabase.com) (free tier 500 MB)
2. `Project Settings → Database → Connection string` (URI)
3. Reemplaza prefijo: `postgresql://` → `postgresql+psycopg://` (solo para Python; el dashboard usa el original)
4. `DATABASE_URL=postgresql+psycopg://... uv run alembic upgrade head`

### Vercel (Dashboard)

```bash
cd dashboard
npx vercel
# Settings → Environment Variables → DATABASE_URL = tu URI Supabase
# Re-deploy
```

### GitHub Actions (Cron diario)

1. Push a GitHub
2. Settings → Secrets and variables → Actions:
   - `DATABASE_URL` (URI Supabase, con prefijo `postgresql+psycopg://`)
   - `TELEGRAM_BOT_TOKEN` (opcional)
3. El workflow `.github/workflows/scrape-daily.yml` corre a las 08:00 UTC (04:00 Chile)
4. Manual: pestaña Actions → "scrape-daily" → Run workflow

## 📐 Modelo de datos

```
perfumes            (canónico: brand + name + volume_ml + concentration)
listings            (1:N — un perfume en N tiendas)
price_history       (time-series, BRIN index)
alerts              (perfume_id + target_price + telegram_chat_id)
scrape_runs         (logs de cada ejecución)
```

## 🛡 Tácticas anti-bot

- **Shopify / Jumpseller** — request directo (`httpx` / `curl_cffi`)
- **Paris / Falabella / Ripley** — `curl_cffi` con `impersonate=chrome131` pasa los WAFs sin necesidad de browser real
- **MercadoLibre** — Playwright + `playwright-stealth` (su WAF detecta TLS de Python plano)
- **Verificador de URLs** — 1 request por dominio en serie, solo HTTP 4xx (404/410) cuenta como muerto. Cualquier transitorio se trata como vivo
- **GitHub Actions caveat** — las IPs son datacenter. Si Falabella o Ripley empiezan a bloquear, considera mover esos a un cron local

## 📁 Estructura

```
scrapers/                       # Python package
  base.py                       # BaseScraper + pipeline + ScrapeRun logging
  config.py                     # pydantic-settings
  db.py                         # SQLAlchemy session
  models.py                     # Perfume, Listing, PriceHistory, Alert, ScrapeRun
  normalize.py                  # parser de títulos crudos → canonical_slug
  matcher.py                    # fuzzy match cross-store (rapidfuzz)
  shopify.py / jumpseller.py / mercadolibre.py / paris.py / ripley.py / falabella.py
  verify_urls.py                # validador HTTP per-dominio
  alerts.py                     # Telegram bot + check_and_send_alerts
  run_all.py                    # orquestador paralelo

alembic/                        # migraciones DB

dashboard/                      # Next.js app
  app/
    layout.tsx                  # wordmark ESSENCE + nav
    page.tsx                    # catálogo con filtros + tabla editorial
    perfume/[id]/page.tsx       # ficha con histórico + comparativa
    alerts/page.tsx             # gestión de alertas
    api/suggest/route.ts        # autocomplete de búsqueda
    api/alerts/route.ts         # CRUD de alertas
  components/                   # Combobox, SearchBox, PriceChart, AlertForm
  lib/                          # db.ts, utils.ts

.github/workflows/scrape-daily.yml
docker-compose.yml              # postgres local
pyproject.toml                  # uv
```

## 🤝 Contribuir

PRs y forks son bienvenidos. El proyecto es personal (tracker de perfumes en Chile) pero la arquitectura sirve como base para cualquier comparador multi-retailer.

## ⚖️ Licencia

MIT. Ver [LICENSE](LICENSE).
