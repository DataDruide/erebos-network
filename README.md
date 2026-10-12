# Erebos Network

> **Ein neuartiges anonymes Netzwerk mit adaptiven Sektoren, Mixnet, dezentraler Governance und Post-Quanten-Kryptographie**

[![Tests](https://github.com/DataDruide/erebos-network/actions/workflows/test.yml/badge.svg)](https://github.com/DataDruide/erebos-network/actions/workflows/test.yml)
[![Lint](https://github.com/DataDruide/erebos-network/actions/workflows/lint.yml/badge.svg)](https://github.com/DataDruide/erebos-network/actions/workflows/lint.yml)
[![Docs](https://github.com/DataDruide/erebos-network/actions/workflows/docs.yml/badge.svg)](https://github.com/DataDruide/erebos-network/actions/workflows/docs.yml)
[![Status: Prototyp](https://img.shields.io/badge/Status-Prototyp-orange.svg)]()
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)]()
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL%202.0-brightgreen.svg)]()

Erebos Network ist ein Forschungsprototyp fuer ein anonymes Netzwerk,
das Tor und I2P als Grundlage nutzt und um sieben neuartige Komponenten
erweitert - darunter Post-Quanten-Kryptographie (NIST Level 5).

---

## Was macht Erebos anders?

| Feature | Tor | I2P | Nym | Erebos |
|---------|-----|-----|-----|--------|
| Onion-Routing | Ja | Nein | Ja | Ja |
| Garlic-Routing | Nein | Ja | Nein | Ja |
| Adaptive Sektoren | Nein | Nein | Nein | Ja |
| Mixnet-Integration | Nein | Nein | Ja | Ja |
| DHT-Discovery | Nein | Nein | Ja | Ja |
| Dezentrale Governance | Nein | Nein | Teilweise | Ja |
| Eingebautes Payment | Nein | Nein | Ja | Ja |
| Browser integriert | Ja | Nein | Nein | Ja |
| Post-Quanten (NIST 5) | Nein | Nein | Nein | Ja |

Erebos ist das erste Darknet mit vollstaendiger Post-Quanten-Kryptographie
auf NIST Level 5.

---

## Die 7 Phasen

### Phase 1: Router + Adaptive Sektoren

Der Erebos-Router entscheidet, wie Traffic geroutet wird:

- Clearnet -> Tor-Exit
- eepSite -> I2P-Tunnel
- Erebos-Peer -> direkt

Und mit welchem Sektor (Anonymitaets-Level):

| Sektor | Hops | Anonymitaet | Latenz | Nutzung |
|--------|------|-------------|--------|---------|
| Schnell | 2 | 4/10 | 300ms | Surfen |
| Standard | 3 | 7/10 | 800ms | Alltag |
| Hoch | 5 | 9/10 | 2s | Sensibel |
| Mixnet | 7 | 10/10 | 5s | Extrem |

### Phase 2: Mixnet-Layer

Schutz gegen Traffic-Correlation:

- Padding - Nachrichten auf 1024B-Blockgroesse
- Delay - zufaellige Verzoegerungen
- Batching - Nachrichten in Gruppen
- Cover-Traffic - Dummy-Nachrichten

### Phase 3: DHT + Peer-Discovery

Dezentrales Peer-Verzeichnis:

- Kademlia-DHT - 256-Bit Keys, K-Buckets
- Peer-Discovery - Bootstrap + Lookup
- .erebos-Naming - SHA-256-basierte Domain-Aufloesung

### Phase 4: Dezentrale Governance

Sybil-Schutz + Abstimmung:

- Proof-of-Work - SHA-256 mit N fuehrenden Nullen
- Reputation - gewichteter Durchschnitt + Decay
- Konsens - Vorschlaege, Quorum, Approval

### Phase 5: Monero-Payment

Anonymes Payment:

- Monero-Wallet - Zahlungsanfragen, Balance
- Payment-System - Angebote, Bestellungen
- Atomic Swaps - Peer-zu-Peer-Handel

### Phase 6: HTTP-API + Browser-Integration

Verbindung zum Browser:

- HTTP-API - /status, /route, /resolve, /stats
- Browser-UI - Network-Status, Sektor-Auswahl

### Phase 7: Post-Quanten-Kryptographie

NIST Level 5:

- ML-KEM-1024 (FIPS 203) - Schluesselaustausch
- SLH-DSA-SHA2-256s (FIPS 205) - Signaturen
- Threefish-512 - symmetrische Verschluesselung (256-Bit PQ)

---

## Installation

    git clone https://github.com/DataDruide/erebos-network.git
    cd erebos-network
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

## Verwendung

### Demo

    python -m erebos_network --demo

### API-Server

    python -m erebos_network --serve --port 9050

Dann testen:

    curl http://127.0.0.1:9050/status
    curl "http://127.0.0.1:9050/route?target=https://example.com"
    curl "http://127.0.0.1:9050/route?target=http://forum.i2p&sector=mixnet"
    curl "http://127.0.0.1:9050/resolve?name=forum.erebos"
    curl http://127.0.0.1:9050/stats

### Tests

    pytest -v

136 Tests, alle gruen.

---

## Architektur

    src/erebos_network/
        router.py        # Routing-Entscheidungen
        sectors.py       # Adaptive Sektoren
        proxy.py         # Lokaler Proxy
        mixnet.py        # Mixnet-Layer
        padding.py       # Padding
        delay.py         # Verzoegerungen
        batching.py      # Batching
        cover.py         # Cover-Traffic
        dht.py           # Kademlia-DHT
        discovery.py     # Peer-Discovery
        naming.py        # .erebos-Naming
        peer.py          # ErebosPeer
        pow.py           # Proof-of-Work
        reputation.py    # Reputation-System
        consensus.py     # Konsens-Protokoll
        governance.py    # Governance
        wallet.py        # Monero-Wallet
        payment.py       # Payment-System
        swap.py          # Atomic Swaps
        api.py           # HTTP-API-Server
        crypto/
            pq_kem.py    # ML-KEM-1024
            pq_sig.py    # SLH-DSA-SHA2-256s
            threefish.py # Threefish-512
            hybrid.py    # Hybrid-Krypto

---

## Dokumentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Technische Architektur
- [THREAT_MODEL.md](docs/THREAT_MODEL.md) - Bedrohungsmodell
- [PQ_CRYPTO.md](docs/PQ_CRYPTO.md) - Post-Quanten-Kryptographie
- [ROADMAP.md](docs/ROADMAP.md) - Roadmap

---

## Roadmap

- [x] Phase 1: Router + Adaptive Sektoren
- [x] Phase 2: Mixnet-Layer
- [x] Phase 3: DHT + Peer-Discovery + Naming
- [x] Phase 4: Dezentrale Governance
- [x] Phase 5: Monero-Payment
- [x] Phase 6: HTTP-API + Browser-Integration
- [x] Phase 7: Post-Quanten-Kryptographie
- [ ] Phase 8: Paper schreiben (arXiv)
- [ ] Phase 9: Community aufbauen
- [ ] Phase 10: Netzwerk-Deployment

---

## Lizenz

MPL 2.0 - siehe LICENSE

## Danksagung

- Tor Project - Onion-Routing
- I2P - Garlic-Routing
- Nym - Mixnet-Forschung
- NIST - Post-Quanten-Standards
- Monero - Anonymes Payment
