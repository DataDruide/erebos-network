#!/bin/bash
# Diagnose-Skript: Startet alle Dienste und zeichnet den genauen Fehler auf.

echo "=== 1. Alles killen ==="
pkill -9 -f "erebos_network --peer"
pkill -9 -f "erebos_network --proxy"
pkill -9 -f "create_test_hidden_service.py"
sleep 3

echo ""
echo "=== 2. Logs leeren ==="
> /tmp/peer1.log
> /tmp/peer2.log
> /tmp/peer3.log
> /tmp/proxy.log
> /tmp/hidden_service.log

echo ""
echo "=== 3. Peers starten ==="
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
echo "=== 4. Proxy starten ==="
nohup python -m erebos_network --proxy --proxy-port 4448 -v > /tmp/proxy.log 2>&1 &
sleep 2

echo ""
echo "=== 5. Test-Hidden-Service starten (im Hintergrund) ==="
nohup python scripts/create_test_hidden_service.py > /tmp/hidden_service.log 2>&1 &
sleep 5

echo ""
echo "=== 6. Adresse aus dem Hidden-Service-Log extrahieren ==="
ADDRESS=$(grep "Hidden Service Adresse:" /tmp/hidden_service.log | awk '{print $4}')
if [ -z "$ADDRESS" ]; then
    echo "❌ Keine Adresse gefunden! Log:"
    cat /tmp/hidden_service.log
    exit 1
fi
echo "✅ Adresse: $ADDRESS"

echo ""
echo "=== 7. curl-Test (mit vollem Output) ==="
curl --socks5-hostname 127.0.0.1:4448 -v "http://$ADDRESS" -o /dev/null 2>&1

echo ""
echo "=== 8. Diagnose: Alle Logs ==="
echo ""
echo "--- Hidden-Service-Log (letzte 20 Zeilen) ---"
tail -20 /tmp/hidden_service.log
echo ""
echo "--- Proxy-Log (letzte 20 Zeilen) ---"
tail -20 /tmp/proxy.log
echo ""
echo "--- Peer 9999 (Rendezvous-Punkt, letzte 20 Zeilen) ---"
tail -20 /tmp/peer1.log
echo ""
echo "--- Peer 9997 (Intro-Point, letzte 10 Zeilen) ---"
tail -10 /tmp/peer3.log
