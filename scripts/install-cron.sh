#!/usr/bin/env bash
# Instala el scraper como cron diario en macOS (launchd)
# Uso: ./scripts/install-cron.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_SRC="$PROJECT_DIR/scripts/cl.essence.scraper.plist"
PLIST_DST="$HOME/Library/LaunchAgents/cl.essence.scraper.plist"
ENV_FILE="$PROJECT_DIR/.env"
LOG_DIR="$PROJECT_DIR/_logs"

echo "📦 Instalando cron de scraping ESSENCE"
echo "   Proyecto: $PROJECT_DIR"

# 1. Verificar .env existe con DATABASE_URL
if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ No existe $ENV_FILE"
    echo "   Crea uno con tu DATABASE_URL de Supabase:"
    echo "   echo 'DATABASE_URL=postgresql+psycopg://...' > $ENV_FILE"
    exit 1
fi
if ! grep -q "^DATABASE_URL=" "$ENV_FILE"; then
    echo "❌ $ENV_FILE no tiene DATABASE_URL"
    exit 1
fi
echo "✅ .env con DATABASE_URL encontrado"

# 2. Verificar uv instalado
if ! command -v uv >/dev/null 2>&1; then
    echo "❌ uv no instalado. Instala con: brew install uv"
    exit 1
fi
echo "✅ uv disponible"

# 3. Crear carpeta de logs
mkdir -p "$LOG_DIR"
echo "✅ $LOG_DIR creada"

# 4. Renderizar plist reemplazando placeholder
mkdir -p "$(dirname "$PLIST_DST")"
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$PLIST_SRC" > "$PLIST_DST"
echo "✅ plist instalada en $PLIST_DST"

# 5. Cargar (si ya estaba cargada, descarga primero)
if launchctl list | grep -q "cl.essence.scraper"; then
    echo "♻️  Descargando versión previa…"
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi
launchctl load -w "$PLIST_DST"
echo "✅ launchd job cargado"

# 6. Verificar
sleep 1
if launchctl list | grep -q "cl.essence.scraper"; then
    echo
    echo "🎉 Listo. El scraper correrá todos los días a las 04:00 hora del Mac."
    echo "   Logs en: $LOG_DIR/scrape.log"
    echo
    echo "💡 Para correrlo AHORA manualmente:"
    echo "   launchctl start cl.essence.scraper"
    echo
    echo "💡 Para ver el próximo trigger:"
    echo "   launchctl print gui/\$UID/cl.essence.scraper | grep -A2 next"
    echo
    echo "💡 Para desinstalar:"
    echo "   ./scripts/uninstall-cron.sh"
else
    echo "❌ No se pudo cargar el launchd job. Revisa con:"
    echo "   launchctl print gui/\$UID/cl.essence.scraper"
    exit 1
fi
