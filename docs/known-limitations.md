# Bekannte Limitierungen

## Parallele Rendezvous-Verbindungen: ✅ unterstuetzt (seit Schritt 3)

Der Rendezvous-Punkt unterstuetzt jetzt mehrere gleichzeitige Clients
pro Hidden-Service-Key:

- `rendezvous_pairs[key]["hidden"]` — ein Eintrag (ein Hidden-Service pro Key)
- `rendezvous_pairs[key]["clients"]` — Liste von Clients
- `rendezvous_pairs[key]["streams"]` — Map stream_id -> {"client": (r,w,c)}

Der Proxy vergibt pro eingehender SOCKS5-Verbindung eine eindeutige
Stream-ID (`conn_id & 0xFFFF`) und filtert eingehende Antworten auf
diese ID. FRAME_DATA im Rendezvous-Pfad traegt `[stream_id: 2B][payload]`.

Test: Zwei parallele `curl`-Aufrufe gegen denselben Hidden-Service
liefern beide HTTP 200 mit 22 Bytes.

## Stream-ID-Kollisionen bei > 65535 Verbindungen

Die Stream-ID ist 2 Bytes breit. Bei mehr als 65535 gleichzeitigen
Proxy-Verbindungen wuerde sie ueberlaufen. Praktisch irrelevant,
aber bei extremen Lasten zu beachten.

## Weitere offene Punkte

- Produktiver Hidden-Service statt `create_test_hidden_service.py`
- Cleanup von `rendezvous_pairs` beim Verbindungsende (Memory-Leak bei
  langer Laufzeit)
- Persistenz der DHT ueber Peer-Neustarts hinweg
