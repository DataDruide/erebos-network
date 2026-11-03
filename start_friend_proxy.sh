#!/bin/bash

PROJECT_DIR="$HOME/Projects/erebos-network"
PEER="167.233.111.144:9996"
PROXY_PORT=4448

cd "$PROJECT_DIR"

echo "Starte Erebos-Proxy (verbinde mit $PEER)..."
source .venv/bin/activate
set -a
. ./.env 2>/dev/null || true
set +a

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

python -m erebos_network --proxy --proxy-port $PROXY_PORT -v
