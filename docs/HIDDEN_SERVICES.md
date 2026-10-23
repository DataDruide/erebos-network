# Erebos Hidden Services

Erebos unterstützt eigene Hidden Services mit `.erebos`-Adressen.
Das Konzept ist an Tor-Onion-Services angelehnt, aber auf die
Erebos-Architektur zugeschnitten (PQ-Handshake, Cover-Traffic,
eigene DHT).

## Überblick

Ein Hidden Service ist ein Dienst, der ohne öffentliche IP-Adresse
erreichbar ist. Die Verbindung wird über einen Rendezvous-Punkt
aufgebaut, sodass weder Client noch Dienst ihre IP preisgeben.

## Adressformat

Eine `.erebos`-Adresse ist ein SHA-256-Hash des Ed25519-Public-Keys,
base32-kodiert (52 Zeichen) plus `.erebos`:

```
mfrggzdfmztwq2lk...erebos
```

Die Adresse ist 256 Bit lang (wie Tor v3) und kollisionsfrei.

## Komponenten

| Komponente | Datei | Aufgabe |
|---|---|---|
| Adressformat | `hidden_service.py` | `.erebos`-Adresse ableiten |
| Descriptor | `hidden_service.py` | Signierte Metadaten (Intro-Points, TTL) |
| Rendezvous | `rendezvous.py` | Request/Response-Strukturen |
| Client | `hidden_service_client.py` | Descriptor holen, Request bauen |
| Intro-Point | `intro_point.py` | Request an Hidden Service weiterleiten |
| Hidden Service | `hidden_service_server.py` | Request verarbeiten, Tunnel aufbauen |
| DHT | `distributed_dht.py` | Descriptor-Verteilung über Kademlia |
| Tunnel | `tunnel.py` | Frame-Typen, Sende/Empfangs-Methoden |

## Ablauf

```
Client                    Intro-Point              Hidden Service
  |                           |                         |
  |-- Descriptor holen ------>| (DHT)                   |
  |                           |                         |
  |-- Rendezvous-Request ---->|                         |
  |                           |-- Request weiter ------>|
  |                           |                         |
  |                           |<-- Tunnel aufbauen -----|
  |<-- Antwort ---------------|<-- Antwort -------------|
```

## Frame-Typen

| Frame-Typ | Wert | Aufgabe |
|---|---|---|
| `FRAME_RENDEZVOUS_REQUEST` | 0x10 | Rendezvous-Anfrage |
| `FRAME_RENDEZVOUS_RESPONSE` | 0x11 | Rendezvous-Antwort |
| `FRAME_DHT_PUT` | 0x12 | Descriptor speichern |
| `FRAME_DHT_GET` | 0x13 | Descriptor abrufen |

## Tests

```bash
pytest tests/test_hidden_service.py
pytest tests/test_rendezvous.py
pytest tests/test_hidden_service_client.py
pytest tests/test_hidden_service_server.py
pytest tests/test_rendezvous_network.py
pytest tests/test_dht_e2e.py
pytest tests/test_proxy_erebos_e2e.py
```

## Nächste Schritte

- [ ] Echte verteilte DHT (Netzwerk-Put/Get statt lokalem Store)
- [ ] Hidden-Service-API (Dienste können sich registrieren)
- [ ] Persistente Descriptors (TTL-basierte Cleanup)
- [ ] Multi-Intro-Point-Rotation
