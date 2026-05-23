#!/usr/bin/env bash
set -euo pipefail
PLIST_DST="$HOME/Library/LaunchAgents/cl.essence.scraper.plist"
if [[ -f "$PLIST_DST" ]]; then
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    rm "$PLIST_DST"
    echo "✅ Cron desinstalado"
else
    echo "ℹ️  No estaba instalado"
fi
