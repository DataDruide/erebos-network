#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Lock: verhindert parallele Backups (Disk-DoS-Schutz)
LOCK_FILE=".backup.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "FEHLER: Ein Backup laeuft bereits (Lock: $LOCK_FILE)"
    exit 1
fi
# Lock-File bleibt liegen: flock wird beim Prozessende automatisch
# freigegeben. Ein rm im Trap waere race-y bei parallelen Laeufen.

TS=$(date +%Y%m%d-%H%M%S)
BK="backups/erebos-$TS"
mkdir -p "$BK"

echo "[1/3] forum.db (SQLCipher-Export)"
docker-compose exec -T hidden-service python3 -c "
import os
from sqlcipher3 import dbapi2 as sqlcipher

key = os.environ.get('EREBOS_DB_KEY', '')
if not key:
    print('FEHLER: EREBOS_DB_KEY nicht gesetzt')
    raise SystemExit(1)

src = '/app/forum.db'
dst = '/tmp/forum.db.backup'

conn = sqlcipher.connect(src)
conn.execute(f\"PRAGMA key='{key}'\")
conn.execute('PRAGMA cipher_compatibility = 4')
conn.execute(f\"ATTACH DATABASE '{dst}' AS backup KEY '{key}'\")
conn.execute('PRAGMA backup.cipher_compatibility = 4')
conn.execute(\"SELECT sqlcipher_export('backup')\")
conn.execute('DETACH DATABASE backup')
conn.close()
print('SQLCipher-Export OK')
"
docker-compose cp hidden-service:/tmp/forum.db.backup "$BK/forum.db"
docker-compose exec -T hidden-service rm -f /tmp/forum.db.backup

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
echo "WICHTIG: Backup enthaelt alle Privkeys — verschluesselt speichern!"
