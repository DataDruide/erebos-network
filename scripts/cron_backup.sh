#!/usr/bin/env bash
# Cron-Wrapper fuer backup.sh.
#
# Aufruf per Cron (z.B. taeglich um 3 Uhr):
#   0 3 * * * /pfad/zu/erebos-network/scripts/cron_backup.sh
#
# Loggt nach /var/log/erebos-backup.log (Fallback: ./backups/cron.log).
# Loescht alte Backups (>KEEP_DAYS Tage).
set -euo pipefail

cd "$(dirname "$0")/.."

LOG="${EREBOS_BACKUP_LOG:-/var/log/erebos-backup.log}"
BACKUP_DIR="backups"
KEEP_DAYS="${EREBOS_BACKUP_KEEP_DAYS:-30}"

# Fallback, falls /var/log nicht beschreibbar
if ! touch "$LOG" 2>/dev/null; then
    LOG="$BACKUP_DIR/cron.log"
    mkdir -p "$BACKUP_DIR"
fi

mkdir -p "$BACKUP_DIR"

{
    echo "=== $(date -Iseconds) ==="
    ./scripts/backup.sh
    echo ""

    if [ -d "$BACKUP_DIR" ]; then
        deleted=$(find "$BACKUP_DIR" -maxdepth 1 -type d -name "erebos-*" \
                  -mtime +"$KEEP_DAYS" -print -exec rm -rf {} \; 2>/dev/null | wc -l | tr -d ' ')
        if [ "$deleted" -gt 0 ]; then
            echo "Alte Backups (>$KEEP_DAYS Tage): $deleted geloescht"
        fi
    fi
    echo "Fertig."
    echo ""
} >> "$LOG" 2>&1
