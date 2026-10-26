#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <backup-dir>"
  echo "Beispiel: $0 backups/erebos-20261026-120000"
  exit 1
fi

BK="$1"
if [ ! -d "$BK" ] || [ ! -f "$BK/forum.db" ]; then
  echo "FEHLER: $BK/forum.db fehlt"
  exit 1
fi

cd "$(dirname "$0")/.."

echo "WARNUNG: Dies ueberschreibt forum.db, hs-keys und wiki.json."
read -p "Fortfahren? [y/N] " ans
if [ "$ans" != "y" ]; then
  echo "Abgebrochen."
  exit 0
fi

echo "[1/5] Container stoppen"
docker-compose stop hidden-service

echo "[2/5] forum.db ersetzen"
cp "$BK/forum.db" ./forum.db

echo "[3/5] hs-keys ersetzen"
if [ -f "$BK/hs-keys.tar.gz" ]; then
  docker run --rm \
    -v erebos-network_hs-keys:/data \
    -v "$PWD/$BK":/backup:ro \
    alpine sh -c "rm -rf /data/* && tar xzf /backup/hs-keys.tar.gz -C /data"
else
  echo "  (kein hs-keys.tar.gz im Backup - uebersprungen)"
fi

echo "[4/5] wiki.json ersetzen"
cp "$BK/wiki.json" ./wiki.json

echo "[5/5] Container starten"
docker-compose start hidden-service

echo ""
echo "Restore fertig."
