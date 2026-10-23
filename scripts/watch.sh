#!/bin/bash
# Zeigt alle Logs live an, während curl läuft.

echo "=== Starte Live-Log (Strg+C zum Beenden) ==="
echo ""

# Alle Logs gleichzeitig verfolgen
tail -f /tmp/proxy.log /tmp/hidden_service.log /tmp/peer1.log /tmp/peer3.log 2>/dev/null | while read line; do
    echo "$line"
done
