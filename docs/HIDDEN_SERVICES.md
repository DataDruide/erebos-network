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
| Peer-DHT-Persistenz | `dht.py` (`PeerDhtStore`) | Descriptor überlebt Neustart |
| Hidden-Service-Runtime | `hidden_service_runtime.py` | Produktiver HS |
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

## Produktiver Hidden-Service (HiddenServiceRuntime)

Die Klasse `HiddenServiceRuntime` in `hidden_service_runtime.py` ist die produktive Implementierung. Sie ist konfigurierbar (Rendezvous, HTTP-Backend, Intro-Points, DHT-Peers, TTL), nutzt `logging` statt `print()` und hat ein sauberes `stop()`.

## DHT-Verteilung: `dht_peers`-Format

`HiddenServiceRuntime._publish_descriptor` verteilt den Descriptor an
alle Peers in `dht_peers`. Zwei Formate werden akzeptiert:

| Format | Beispiel | Bedeutung |
|---|---|---|
| reiner Port (int) | `9999` | Verbindet zu `rendezvous_host:9999` |
| `host:port` (str) | `172.20.0.10:9999` | Verbindet zu `172.20.0.10:9999` |

**Empfehlung**: In verteilten Setups (Docker, echte Peers) immer
`host:port` nutzen, damit der Descriptor an **alle** Peers geht:

    --dht-peers 172.20.0.10:9999,172.20.0.11:9998,172.20.0.12:9997

Mit reinen Ports landet der Descriptor nur bei `rendezvous_host` — bei
Ausfall dieses Peers ist der Hidden-Service dann nicht mehr auffindbar.

## DHT-Persistenz (PeerDhtStore)

`PeerDhtStore` in `dht.py` persistiert die Peer-DHT in `/tmp/erebos_peer_dht_<port>.json` (atomar via tmp+rename). Nach einem Peer-Neustart wird der Descriptor geladen, ohne neuen DHT-PUT.

## Parallele Verbindungen (Stream-Registry)

Der Rendezvous-Punkt unterstuetzt mehrere Clients pro Key. Jeder Client vergibt pro SOCKS5-Verbindung eine eindeutige `stream_id` (`conn_id & 0xFFFF`). FRAME_DATA traegt `[stream_id: 2B][payload]`.

## Ende-zu-Ende-Verschluesselung

Seit dem E2E-Patch (B2+B3+B4) handeln Client und Hidden-Service
einen gemeinsamen Schluessel aus, der peer1 nicht bekannt ist:

1. Client sendet FRAME_DATA mit e2e_flag=0x02 (E2E_KEY_INIT,
   X25519_pub + ML-KEM_pub).
2. Hidden-Service antwortet mit e2e_flag=0x03 (E2E_KEY_RESP,
   X25519_pub + ML-KEM_ct).
3. Beide leiten e2e_key = HKDF(x25519_shared || mlkem_shared,
   info=erebos-e2e-key-v1) ab.
4. HTTP-Anfrage und -Antwort werden mit ChaCha20-Poly1305 und
   e2e_flag=0x01 verschluesselt.

peer1 leitet die Frames roh weiter (nur Tunnel-Re-Encryption) und
sieht keinen HTTP-Klartext. Die E2E-Schicht ist undurchsichtig fuer
den Rendezvous-Punkt.

Beweis: peer1.log enthaelt e2e_flag=0x1-Meldungen, aber keinen
HTTP-Klartext.

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

- [x] Persistente Descriptors in Peers (PeerDhtStore, Punkt 4)
- [x] Parallele Verbindungen (Stream-Registry, Punkt 3)
- [x] Produktiver Hidden-Service als Modul (HiddenServiceRuntime, Punkt 2)
- [ ] Hidden-Service-Reconnect nach Peer-Neustart
- [ ] Persistente Hidden-Service-Schluessel
- [ ] Echte verteilte DHT
- [ ] Multi-Intro-Point-Rotation
- [x] Ende-zu-Ende-Verschluesselung (E2E_KEY_INIT/RESP, ChaCha20-Poly1305)
