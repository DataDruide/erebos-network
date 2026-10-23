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
source .venv/bin/activate
export EREBOS_PEER_HOST=0.0.0.0

# Peers
nohup python -m erebos_network --peer --peer-port 9997 --ack-cover -v > /tmp/peer3.log 2>&1 &
sleep 2
nohup python -m erebos_network --peer --peer-port 9998 --ack-cover -v > /tmp/peer2.log 2>&1 &
sleep 2
nohup python -m erebos_network --peer --peer-port 9999 --ack-cover -v > /tmp/peer1.log 2>&1 &
sleep 3

# Proxy
nohup python -m erebos_network --proxy --proxy-port 4448 -v > /tmp/proxy.log 2>&1 &
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
python scripts/create_test_hidden_service.py
