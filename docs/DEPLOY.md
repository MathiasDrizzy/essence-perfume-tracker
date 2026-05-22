# Deploy gratis (paso a paso)

Resultado esperado: dashboard público en Vercel, base en Supabase, cron diario en GitHub Actions. **Costo: $0** dentro de los free tiers.

---

## 1. Subir a GitHub

```bash
cd "/Users/drizzy/Documents/project/dashboard perfumes"
git init
git add .
git commit -m "init: ESSENCE perfume tracker"
gh repo create essence-perfume-tracker --public --source=. --push
# (si no tienes gh CLI: crea el repo en github.com y `git remote add` + `git push -u`)
```

> ⚠️ Antes del primer push verifica `git status` — no debe aparecer `.env` ni nada con secretos.

---

## 2. Supabase (Postgres gratis)

1. [supabase.com](https://supabase.com) → New project → región `South America (São Paulo)`
2. Espera ~2 min al provision
3. **Project Settings → Database → Connection string → URI**
4. Copia el string. Reemplazo el prefijo:
   - Para **Python (scrapers + Alembic)**: `postgresql://...` → `postgresql+psycopg://...`
   - Para **Next.js dashboard**: usa el URI original `postgresql://...`
5. Aplica el schema desde tu Mac (una vez):
   ```bash
   DATABASE_URL='postgresql+psycopg://postgres.xxx:pwd@aws-0-sa-east-1.pooler.supabase.com:6543/postgres' \
   uv run alembic upgrade head
   ```

> Free tier: 500 MB. Con ~50.000 listings + 6 meses de price_history estás usando ~80 MB. Margen sobrado.

---

## 3. Vercel (dashboard)

```bash
cd dashboard
npx vercel link             # asocia con tu cuenta
npx vercel env add DATABASE_URL production
# pega el URI Supabase (sin el +psycopg)
npx vercel --prod
```

O alternativa **sin CLI**:
1. vercel.com → Add new project → importa tu repo GitHub
2. Root directory: `dashboard`
3. Framework preset: Next.js (auto-detecta)
4. Environment variables → `DATABASE_URL` = URI Supabase
5. Deploy

Tu dashboard queda en `https://<repo>.vercel.app`.

---

## 4. GitHub Actions (cron diario)

1. En tu repo GitHub: **Settings → Secrets and variables → Actions → New repository secret**
   - `DATABASE_URL` = URI Supabase con `+psycopg`
   - `TELEGRAM_BOT_TOKEN` (opcional, para alertas)
2. El workflow `.github/workflows/scrape-daily.yml` ya está. Corre a las 08:00 UTC (04:00 Chile).
3. **Forzar ejecución ahora**: pestaña Actions → "scrape-daily" → Run workflow

---

## 5. Telegram bot (opcional)

```bash
# Crear el bot
# 1. Telegram → @BotFather → /newbot
# 2. Guarda el token

# Obtener tu chat_id
# Localmente (necesita TELEGRAM_BOT_TOKEN en .env):
uv run python -m scrapers.alerts bot
# Escríbele /start a tu bot → te responde con tu chat_id
# Detén el comando (Ctrl+C)

# Usa ese chat_id al crear alertas en https://<repo>.vercel.app/alerts
```

El cron del scraper en GH Actions dispara las alertas Telegram automáticamente al final de cada corrida.

---

## Checklist final

- [ ] Git repo creado y pushed
- [ ] `.env` y `.env.local` NO fueron commiteados (`git log --all -- .env` debe estar vacío)
- [ ] Supabase creado, URI guardado
- [ ] `alembic upgrade head` ejecutado contra Supabase
- [ ] Vercel project deployado con `DATABASE_URL`
- [ ] GitHub Actions secrets configurados
- [ ] Workflow ejecutado manualmente al menos una vez sin errores
- [ ] (opcional) Bot Telegram funcionando

---

## Troubleshooting

**Vercel build falla con error de tipos**
```bash
cd dashboard && pnpm build  # repro local. Arregla errores antes de pushear.
```

**Supabase rate limit con muchas escrituras**
- El plan free tier permite ~60 inserts/seg sostenidos. Con 50k inserts en un run el cron tarda ~15 min en escribir DB (no en scrapear).
- Si ves errores, baja `--workers` en el workflow a `3`.

**GH Actions falla con "playwright browser not found"**
- Borra el cache de Playwright en tu repo (Settings → Actions → Caches) y re-corre.
- El cache key es `playwright-Linux-chromium`.

**Falabella o Ripley bloquean desde GH Actions**
- Las IPs de Actions son datacenter. Es raro pero posible.
- Workaround: corre esos scrapers como cron local con `crontab` o pasa a Bright Data proxies.
