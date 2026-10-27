#!/bin/bash
# Startet alle Erebos-Dienste neu und validiert den Status.

echo "=== 1. Alle Erebos-Prozesse killen ==="
pkill -9 -f "erebos_network --peer"
pkill -9 -f "erebos_network --proxy"
pkill -9 -f "create_test_hidden_service.py"
sleep 3

echo ""
echo "=== 2. Prüfen, ob alles sauber ist ==="
if ps aux | grep -E "erebos_network|create_test_hidden_service" | grep -v grep > /dev/null; then
    echo "❌ Es laufen noch Prozesse!"
    ps aux | grep -E "erebos_network|create_test_hidden_service" | grep -v grep
    exit 1
else
    echo "✅ Keine Erebos-Prozesse mehr"
fi

echo ""
echo "=== 3. Prüfen, ob Ports frei sind ==="
for PORT in 9996 9997 9998 9999 4448 8080; do
    if lsof -nP -iTCP:$PORT | grep LISTEN > /dev/null; then
        echo "❌ Port $PORT ist noch belegt!"
        lsof -nP -iTCP:$PORT | grep LISTEN
        exit 1
    else
        echo "✅ Port $PORT frei"
    fi
done

echo ""
echo "=== 4. Dienste starten ==="
cd ~/Projects/erebos-network

if [ -f .env ]; then
    set -a
    . ./.env
    set +a
    echo "OK: .env geladen"
fi
source .venv/bin/activate
export EREBOS_PEER_HOST=0.0.0.0

# Peers
nohup .venv/bin/python -m erebos_network --peer --peer-port 9997 --ack-cover -v > /tmp/peer3.log 2>&1 &
sleep 2
nohup .venv/bin/python -m erebos_network --peer --peer-port 9998 --ack-cover -v > /tmp/peer2.log 2>&1 &
sleep 2
nohup .venv/bin/python -m erebos_network --peer --peer-port 9999 --ack-cover -v > /tmp/peer1.log 2>&1 &
sleep 3

# Proxy
nohup .venv/bin/python -m erebos_network --proxy --proxy-port 4448 -v > /tmp/proxy.log 2>&1 &
sleep 2

echo ""
echo "=== 5. Validierung: Laufen die Dienste? ==="
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
echo "=== 6. Test-Hidden-Service starten ==="
echo "Starte Test-Hidden-Service im Vordergrund..."
nohup .venv/bin/python -u scripts/create_test_hidden_service.py > /tmp/hidden_service.log 2>&1 &
sleep 5

echo ""
echo "=== 7. Validierung: Laeuft der Hidden-Service? ==="
if ps aux | grep "create_test_hidden_service" | grep -v grep > /dev/null; then
    echo "✅ Hidden-Service laeuft"
else
    echo "❌ Hidden-Service laeuft NICHT!"
    echo "--- hidden_service.log ---"
    tail -20 /tmp/hidden_service.log
    exit 1
fi

echo ""
echo "=== 8. Validierung: Laeuft der HTTP-Server (Port 8080)? ==="
for i in 1 2 3 4 5 6 7 8 9 10; do
    if lsof -nP -iTCP:8080 | grep LISTEN > /dev/null; then
        PID=$(lsof -nP -iTCP:8080 | grep LISTEN | awk '{print $2}' | head -1)
        echo "✅ Port 8080 laeuft (PID $PID)"
        break
    fi
    if [ "$i" = "10" ]; then
        echo "❌ Port 8080 laeuft NICHT!"
        tail -20 /tmp/hidden_service.log
        exit 1
    fi
    sleep 1
done

echo ""
echo "=== 9. Adresse aus dem Hidden-Service-Log extrahieren ==="
ADDRESS=$(grep "Hidden Service laeuft:" /tmp/hidden_service.log | awk '{print $NF}' | tail -1)
if [ -z "$ADDRESS" ]; then
    ADDRESS=$(grep -oE "[a-z0-9]{52}\.erebos" /tmp/hidden_service.log | tail -1)
fi
if [ -z "$ADDRESS" ]; then
    echo "❌ Keine Adresse gefunden!"
    tail -20 /tmp/hidden_service.log
    exit 1
fi
echo "✅ Adresse: $ADDRESS"

echo ""
echo "=== 10. E2E-Test (curl durch SOCKS5-Proxy) ==="
curl --max-time 15 --socks5-hostname 127.0.0.1:4448 -v "http://$ADDRESS" -o /dev/null 2>&1 | tail -20
CURL_EXIT=$?
if [ $CURL_EXIT -eq 0 ]; then
    echo "✅ E2E-Test erfolgreich"
else
    echo "⚠️  curl-Exit: $CURL_EXIT (Timeout oder Fehler)"
fi

echo ""
echo "=== 11. READY ==="
echo "Alle Dienste laufen. Adresse: $ADDRESS"
echo ""
echo "Zum Testen: curl --socks5-hostname 127.0.0.1:4448 -v http://$ADDRESS -o /dev/null"
echo ""
echo "=== Banner-Check (letzte 10 Zeilen proxy.log) ==="
grep -A8 "RENDEZVOUS HERGESTELLT" /tmp/proxy.log | tail -10

