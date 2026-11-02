#!/bin/bash

# ============================================================
# Erebos Komplett-Start-Skript
# Startet Docker-Stack, Browser und führt einen automatischen Test aus.
# ============================================================

set -e  # Bei Fehler abbrechen

PROJECT_DIR="$HOME/Projects/erebos-network"
LOG_DIR="$PROJECT_DIR/logs"
BROWSER_DIR="$HOME/mullvad-browser-new"
PROXY_PORT=4448

# Log-Verzeichnis anlegen
mkdir -p "$LOG_DIR"

# Zeitstempel für Logs
TS=$(date +"%Y%m%d_%H%M%S")

echo "============================================================"
echo " Erebos Komplett-Start"
echo " Logs: $LOG_DIR"
echo "============================================================"

# 1. Alte Prozesse beenden
echo "[1/6] Beende alte Prozesse..."
pkill -f "erebos_network" 2>/dev/null || true
pkill -f "create_hidden_service" 2>/dev/null || true
pkill -f "Erebos.app/Contents/MacOS/firefox" 2>/dev/null || true
sleep 2

# 2. Docker-Stack komplett neu bauen
echo "[2/6] Baue Docker-Stack neu..."
cd "$PROJECT_DIR"
set -a
. ./.env
set +a
docker compose down -v --rmi all > "$LOG_DIR/docker_down_$TS.log" 2>&1 || true
docker compose up -d --build > "$LOG_DIR/docker_up_$TS.log" 2>&1

# 3. Warten, bis alle Container healthy sind
echo "[3/6] Warte auf Container (max. 120s)..."
TIMEOUT=120
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    HEALTHY=$(docker compose ps --format json | python3 -c "
import sys, json
try:
    data = sys.stdin.read().strip()
    if not data:
        print('0/5')
    else:
        containers = [json.loads(line) for line in data.splitlines() if line.strip()]
        healthy = sum(1 for c in containers if c.get('Health', '') == 'healthy' or c.get('State', '') == 'running')
        print(f'{healthy}/{len(containers)}')
except:
    print('0/5')
")
    echo "  Container-Status: $HEALTHY (nach ${ELAPSED}s)"
    if [[ "$HEALTHY" == "5/5" ]]; then
        break
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

# 4. Kurz warten, damit der Hidden-Service den Descriptor veröffentlicht
echo "[4/6] Warte 15s auf Descriptor-Veröffentlichung..."
sleep 15

# 5. Logs der Container in Dateien schreiben
echo "[5/6] Schreibe Container-Logs..."
for svc in peer1 peer2 peer3 proxy hidden-service; do
    docker compose logs "$svc" > "$LOG_DIR/${svc}_$TS.log" 2>&1
    echo "  $svc -> $LOG_DIR/${svc}_$TS.log"
done

# 6. Automatischer Test über den Proxy
# Adresse aus dem Hidden-Service-Log extrahieren
EREBOS_ADDR=$(docker compose logs hidden-service 2>&1 | grep -oE '[a-z0-9]{52}\.erebos' | tail -1)
if [ -z "$EREBOS_ADDR" ]; then
    echo "WARNUNG: Konnte keine .erebos-Adresse aus den Logs lesen."
    EREBOS_ADDR="unbekannt"
fi
echo "Gefundene .erebos-Adresse: $EREBOS_ADDR"

echo "[6/6] Automatischer Test gegen $EREBOS_ADDR"
echo "----------------------------------------"
TEST_OUTPUT=$(curl -s -o /dev/null -w "HTTP-Status: %{http_code}\nZeit: %{time_total}s\n" \
    --max-time 20 \
    --socks5-hostname 127.0.0.1:$PROXY_PORT \
    "http://$EREBOS_ADDR/" 2>&1)
echo "$TEST_OUTPUT"
echo "$TEST_OUTPUT" > "$LOG_DIR/test_$TS.log"

# Browser starten (optional, im Hintergrund)
echo ""
echo "Starte Browser (python3.11 ./mach run)..."
cd "$BROWSER_DIR"
if [ -f "$BROWSER_DIR/obj-aarch64-apple-darwin/dist/firefox/Erebos.app/Contents/MacOS/firefox" ]; then
    # Browser im Hintergrund starten
    "$BROWSER_DIR/obj-aarch64-apple-darwin/dist/firefox/Erebos.app/Contents/MacOS/firefox" \
        -no-remote -foreground > "$LOG_DIR/browser_$TS.log" 2>&1 &
    echo "  Browser gestartet (PID $!)"
else
    echo "  Browser nicht gefunden unter $BROWSER_DIR"
fi

echo ""
echo "============================================================"
echo " FERTIG"
echo " Öffne im Browser: http://$EREBOS_ADDR/"
echo " Logs: $LOG_DIR"
echo "============================================================"
