#!/usr/bin/env bash
# E2E-Smoke-Test fuer die Mail-Rotation-Reihe.
# Setzt voraus: docker-compose up -d (hidden-service laeuft).

set -uo pipefail   # KEIN set -e: wir wollen selbst pruefen

ADDR="${EREBOS_HS_ADDR:-icxyvzvtc5wcdhzagv5hpxtfgmxqkgyhx5rqy47vrpignubveb4q.erebos}"
COOKIE=/tmp/erebos_smoke_ca
rm -f "$COOKIE"

curl_hs() {
    curl --socks5-hostname localhost:4448 -s -b "$COOKIE" -c "$COOKIE" \
         --max-time 20 "$@"
}

fail() {
    echo "FEHLER: $*" >&2
    exit 1
}

echo "=== 0. Proxy-Erreichbarkeit checken ==="
HTTP=$(curl_hs -o /dev/null -w "%{http_code}" "http://$ADDR/" || true)
echo "GET /: HTTP $HTTP"
if [ "$HTTP" = "000" ]; then
    echo ""
    echo "Proxy/HS antwortet nicht (HTTP 000)."
    echo "Diagnose:"
    echo "  docker-compose ps"
    echo "  docker-compose logs --tail=30 hidden-service"
    echo "  docker-compose logs --tail=30 proxy"
    exit 1
fi

echo ""
echo "=== 1. Neue Session + UUID ==="
HTML=$(curl_hs "http://$ADDR/mail")
if [ -z "$HTML" ]; then
    fail "GET /mail lieferte leeren Body"
fi
MY_UUID=$(echo "$HTML" | grep -oE "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" | head -1)
if [ -z "$MY_UUID" ]; then
    echo "HTML-Auszug (erste 500 Zeichen):"
    echo "$HTML" | head -c 500
    echo ""
    fail "keine UUID in GET /mail gefunden"
fi
echo "UUID: $MY_UUID"

echo ""
echo "=== 2. v1-Mail senden ==="
HTTP=$(curl_hs -o /dev/null -w "%{http_code}" \
    -X POST \
    -d "to_uuid=$MY_UUID&subject=Final-v1&body=Final+Test+v1" \
    "http://$ADDR/mail")
echo "Mail v1: HTTP $HTTP"
[ "$HTTP" = "302" ] || fail "erwartete 302, got $HTTP"

echo ""
echo "=== 3. v1-Mail anzeigen (gruen erwartet) ==="
curl_hs "http://$ADDR/mail" | grep -E "Final-v1|verifiziert" || echo "  (kein Match)"

echo ""
echo "=== 4. Rotation v1 -> v2 ==="
docker-compose exec -T hidden-service python3 -c "
import erebos_network.forum_db as f
keys = f.rotate_mail_keys('$MY_UUID')
print('Rotation: neue Version', keys['key_version'])
" || fail "Rotation fehlgeschlagen"

echo ""
echo "=== 5. Alte v1-Mail (orange erwartet) ==="
curl_hs "http://$ADDR/mail" | grep -E "Final-v1|veraltet|verifiziert|Entschluesselung" || echo "  (kein Match)"

echo ""
echo "=== 6. Neue v2-Mail senden ==="
HTTP=$(curl_hs -o /dev/null -w "%{http_code}" \
    -X POST \
    -d "to_uuid=$MY_UUID&subject=Final-v2&body=Final+Test+v2" \
    "http://$ADDR/mail")
echo "Mail v2: HTTP $HTTP"
[ "$HTTP" = "302" ] || fail "erwartete 302, got $HTTP"

echo ""
echo "=== 7. v2-Mail anzeigen (gruen erwartet) ==="
curl_hs "http://$ADDR/mail" | grep -E "Final-v2|verifiziert" || echo "  (kein Match)"

echo ""
echo "=== 8. Beide zusammen ==="
curl_hs "http://$ADDR/mail" | grep -E "Final-v1|Final-v2" || echo "  (kein Match)"

echo ""
echo "=== Smoke-Test fertig ==="
