#!/bin/bash
# Killt ALLES, startet alles neu, validiert und zeigt "READY".

set -e

echo "=== 1. ALLES killen (Peers, Proxy, Hidden-Service) ==="
pkill -9 -f "erebos_network --peer" 2>/dev/null || true
pkill -9 -f "erebos_network --proxy" 2>/dev/null || true
pkill -9 -f "create_test_hidden_service.py" 2>/dev/null || true
sleep 3

echo ""
echo "=== 2. Validierung: Sind wirklich alle Prozesse weg? ==="
if ps aux | grep -E "erebos_network|create_test_hidden_service" | grep -v grep > /dev/null; then
    echo "❌ Es laufen noch Prozesse!"
    ps aux | grep -E "erebos_network|create_test_hidden_service" | grep -v grep
    exit 1
else
    echo "✅ Keine Erebos-Prozesse mehr"
fi

echo ""
echo "=== 3. Validierung: Sind alle Ports frei? ==="
for PORT in 9997 9998 9999 4448 8080; do
    if lsof -nP -iTCP:$PORT | grep LISTEN > /dev/null; then
        echo "❌ Port $PORT ist noch belegt!"
        lsof -nP -iTCP:$PORT | grep LISTEN
        exit 1
    else
        echo "✅ Port $PORT frei"
    fi
done

echo ""
echo "=== 4. Peers starten ==="
cd ~/Projects/erebos-network
source .venv/bin/activate
export EREBOS_PEER_HOST=0.0.0.0
nohup python -m erebos_network --peer --peer-port 9997 --ack-cover -v > /tmp/peer3.log 2>&1 &
sleep 2
nohup python -m erebos_network --peer --peer-port 9998 --ack-cover -v > /tmp/peer2.log 2>&1 &
sleep 2
nohup python -m erebos_network --peer --peer-port 9999 --ack-cover -v > /tmp/peer1.log 2>&1 &
sleep 3

echo ""
echo "=== 5. Proxy starten ==="
nohup python -m erebos_network --proxy --proxy-port 4448 -v > /tmp/proxy.log 2>&1 &
sleep 2

echo ""
echo "=== 6. Validierung: Laufen Peers und Proxy? ==="
FAIL=0
for PORT in 9997 9998 9999 4448; do
    if lsof -nP -iTCP:$PORT | grep LISTEN > /dev/null; then
        PID=$(lsof -nP -iTCP:$PORT | grep LISTEN | awk '{print $2}' | head -1)
        echo "✅ Port $PORT läuft (PID $PID)"
    else
        echo "❌ Port $PORT läuft NICHT!"
        FAIL=1
    fi
done

if [ $FAIL -ne 0 ]; then
    echo ""
    echo "❌ Nicht alle Dienste laufen. Logs:"
    echo "--- peer3.log ---"; tail -5 /tmp/peer3.log
    echo "--- peer2.log ---"; tail -5 /tmp/peer2.log
    echo "--- peer1.log ---"; tail -5 /tmp/peer1.log
    echo "--- proxy.log ---"; tail -5 /tmp/proxy.log
    exit 1
fi

echo ""
echo "=== 7. Test-Hidden-Service starten (im Hintergrund) ==="
nohup python -u scripts/create_test_hidden_service.py > /tmp/hidden_service.log 2>&1 &
sleep 5

echo ""
echo "=== 8. Validierung: Läuft der Hidden-Service? ==="
if ps aux | grep "create_test_hidden_service" | grep -v grep > /dev/null; then
    echo "✅ Hidden-Service läuft"
else
    echo "❌ Hidden-Service läuft NICHT!"
    echo "--- hidden_service.log ---"
    tail -20 /tmp/hidden_service.log
    exit 1
fi

echo ""
echo "=== 9. Validierung: Laufen HTTP-Server und Rendezvous-Server? ==="
for PORT in 8080; do
    if lsof -nP -iTCP:$PORT | grep LISTEN > /dev/null; then
        PID=$(lsof -nP -iTCP:$PORT | grep LISTEN | awk '{print $2}' | head -1)
        echo "✅ Port $PORT läuft (PID $PID)"
    else
        echo "❌ Port $PORT läuft NICHT!"
        echo "--- hidden_service.log ---"
        tail -20 /tmp/hidden_service.log
        exit 1
    fi
done

echo ""
echo "=== 10. Adresse aus dem Hidden-Service-Log extrahieren ==="
ADDRESS=$(grep "Hidden Service Adresse:" /tmp/hidden_service.log | awk '{print $4}')
if [ -z "$ADDRESS" ]; then
    echo "❌ Keine Adresse gefunden!"
    echo "--- hidden_service.log ---"
    tail -20 /tmp/hidden_service.log
    exit 1
fi
echo "✅ Adresse: $ADDRESS"

echo ""
echo "=== 11. curl-Test ==="
curl --socks5-hostname 127.0.0.1:4448 -v "http://$ADDRESS" -o /dev/null 2>&1

echo ""
echo "=== 12. READY ==="
echo "Alle Dienste laufen. Adresse: $ADDRESS"
echo ""
echo "Zum Testen: curl --socks5-hostname 127.0.0.1:4448 -v http://$ADDRESS -o /dev/null"
