#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

TS=$(date +%Y%m%d-%H%M%S)
BK="backups/erebos-$TS"
mkdir -p "$BK"

echo "[1/3] forum.db (sqlite3 .backup)"
docker-compose exec -T hidden-service python3 -c "
import sqlite3
src = sqlite3.connect('/app/forum.db')
dst = sqlite3.connect('/tmp/forum.db.bak')
src.backup(dst)
dst.close(); src.close()
"
docker-compose cp hidden-service:/tmp/forum.db.bak "$BK/forum.db"
docker-compose exec -T hidden-service rm -f /tmp/forum.db.bak

echo "[2/3] hs-keys (named volume)"
docker run --rm \
  -v erebos-network_hs-keys:/data:ro \
  -v "$PWD/$BK":/backup \
  alpine tar czf /backup/hs-keys.tar.gz -C /data .

echo "[3/3] wiki.json"
cp wiki.json "$BK/wiki.json"

echo ""
echo "Backup fertig: $BK"
echo "Groesse: $(du -sh "$BK" | cut -f1)"
echo ""
echo "WICHTIG: Backup enthaelt alle Privkeys - verschluesselt speichern!"
