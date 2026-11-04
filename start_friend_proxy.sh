#!/bin/bash
# Erebos Proxy-Starter für Freunde
# Verbindet sich mit dem öffentlichen Hetzner-Peer

# 1. Eigenes Verzeichnis erkennen (dort liegt das Skript)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

PEER="167.233.111.144:9996"
PROXY_PORT=4448

# 2. Prüfen, ob das Projektverzeichnis vollständig ist
if [ ! -d "$PROJECT_DIR/src/erebos_network" ]; then
    echo "FEHLER: Das Projektverzeichnis scheint unvollständig zu sein."
    echo "Erwartet: $PROJECT_DIR/src/erebos_network"
    echo ""
    echo "Bitte stelle sicher, dass du das Skript im Projektordner ausführst"
    echo "(dort, wo auch 'src/' und '.venv/' liegen)."
    exit 1
fi

if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "FEHLER: Die virtuelle Umgebung (.venv) fehlt."
    echo "Bitte führe zuerst aus:"
    echo "  cd $PROJECT_DIR"
    echo "  python3.11 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -e ."
    exit 1
fi

cd "$PROJECT_DIR"

echo "Starte Erebos-Proxy (verbinde mit $PEER)..."
source .venv/bin/activate
set -a
. ./.env 2>/dev/null || true
set +a

# Peer-Hosts für Freundes-Setup: alle Peers zeigen auf den Hetzner-Server
export EREBOS_PEER_HOSTS="peer1=167.233.111.144,peer2=167.233.111.144,peer3=167.233.111.144,peer4=167.233.111.144"

# 3. Peers.json für Freunde erstellen (nur Hetzner-Peer)
cat << PEERS > peers.json
{
  "peers": [
    {
      "name": "hetzner-bootstrap",
      "address": "$PEER",
      "peer_id": "0000000000000000000000000000000000000000000000000000000000000000",
      "role": "entry",
      "latency_ms": 50,
      "enabled": true
    }
  ]
}
PEERS

# 4. Proxy starten
python -m erebos_network --proxy --proxy-port $PROXY_PORT -v
