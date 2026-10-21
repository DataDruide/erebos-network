
## 📊 Visuelle Dokumentation

- [Architektur](docs/ARCHITECTURE.md) — 3-Hop-Onion-Netzwerk mit PQC
- [Kryptographie](docs/crypto.md) — Hybrid-Handshake (X25519 + ML-KEM-1024)
- [Cover-Traffic](docs/cover-traffic.md) — Timing-Schutz durch kalibriertes Padding

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

## What is Erebos?

Erebos is a research prototype for an anonymous network that combines
onion routing, mixnet-style timing obfuscation, and post-quantum
cryptography. It is **not** a Tor replacement and **not** a VPN. It is
an experiment in what a 2026-era anonymity system could look like if
it learned from the failure modes of Tor, Nym, and I2P.

**Core ideas:**

- **Hybrid post-quantum handshake** — X25519 + ML-KEM-1024, NIST Level 5
- **Calibrated cover traffic** — parameters measured against real HTTP
  bursts (v0.4.2), not guessed. See ```scripts/analyze_traffic.py```
- **Bidirectional chaff** — reactive drop-cover mirrors downlink bursts,
  ```FRAME_COVER_ACK``` adds symmetric downlink noise
- **Bucket padding on all peer frames** — 256-byte buckets, every
  direction
- **Reproducible builds** — ```make verify``` builds the wheel twice and
  compares content hashes
- **Published threat model** — ```SECURITY.md``` lists defenses, known
  limits, and what an external audit should check

**Status:** Beta (v0.4.2), 700 tests green. Not production-ready.

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
| Hybrid-KEM | Nein | Nein | Nein | Ja |
| Client-Hygiene | Nein | Nein | Ja | Ja |
| DoS-Hardening | Teilweise | Teilweise | Ja | Ja |
| PQ-Sphinx | Nein | Nein | Nein | Ja |
| End-to-End | Teilweise | Ja | Ja | Ja |
| VRF-Reputation | Nein | Nein | Nein | Ja |
| Hidden Services | Ja | Ja | Nein | Ja |
| App-Obfuskation | Nein | Nein | Ja | Ja |
| Eclipse-Schutz | Teilweise | Teilweise | Teilweise | Ja |
| HS-Hardening | Teilweise | Nein | Nein | Ja |
| Reorg-Schutz | Nein | Nein | Nein | Ja |
| ML-Correlation-Schutz | Nein | Nein | Nein | Ja |
| Flow-Splitting | Nein | Nein | Nein | Ja |
| Intro-Point-Rotation | Ja | Nein | Nein | Ja |
| Dynamic PoW | Nein | Nein | Nein | Ja |
| WF-Schutz (TGTO) | Nein | Nein | Nein | Ja |
| Dandelion++ | Nein | Nein | Nein | Ja |
| HS-Obfuskation | Nein | Nein | Nein | Ja |
| TCP-Normalisierung | Nein | Nein | Nein | Ja |

Erebos ist das erste Darknet mit vollstaendiger Post-Quanten-Kryptographie
auf NIST Level 5.

---

## Die Phasen

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

### Phase 8: Security Hardening

Hybrid-Krypto, Poisson-Mixnet, konstanter Cover-Traffic:

- Hybrid-KEM - X25519 + ML-KEM-1024
- Poisson-Mixing - Exponentialverteilung
- Konstanter Cover-Traffic - Unobservability

### Phase 9: Advanced Security

Client-Hygiene, DoS-Schutz, Pfad-Auswahl, PQ-Sphinx:

- Client-Hygiene - Timing-Jitter, Padding, Rate-Limits
- Memory-Hardening - Descriptor-Limits, TTL-Cleanup
- Pfad-Auswahl - alpha-SS, K-HF, K/W
- PQ-Sphinx - Post-Quanten-Mixnet-Format

---

### Phase 10: Final Security Layer

End-to-End, VRF-Reputation, Hidden Services, Obfuskation:

- End-to-End - kein Exit noetig, beide Seiten anonym
- VRF-Reputation - Verifizierbare Ratings, Anti-Framing
- Hidden Services - .erebos-Dienste mit Rendezvous-Punkten
- Anwendungs-Obfuskation - Size-Noise, Protocol-Cover, Timing-Noise

---

### Phase 11: Eclipse Protection

Schutz gegen Eclipse-Angriffe durch IP/Subnetz-Diversity:

- Max. 2 Peers pro /24-Subnetz (IPv4)
- Max. 2 Peers pro /48-Subnetz (IPv6)
- Loopback und Link-Local ausgenommen
- Angreifer braucht 50+ VPS statt 1

### Phase 12: HS Descriptor Hardening

Schutz gegen Descriptor-Flood (Tor 2026):

- Max. 64 KB pro Descriptor
- Max. 10 Descriptors pro Service
- Max. 10.000 Descriptors global
- Rate-Limit: 5 Publish/Minute
- Proof-of-Work (3 führende Nullen)
- TTL-basierte Cleanup

### Phase 13: Monero Reorg Protection

Schutz gegen Chain-Reorganization (Monero 2025):

- Chain-Height-Tracking
- Reorg-Detection (Height-Abnahme)
- Block-Hash-Mismatch-Detection
- Payment-Invalidierung bei Reorg
- Dynamische Bestätigungen:
  - < 10 XMR: 20 Bestätigungen
  - ≥ 10 XMR: 30 Bestätigungen

---

### Phase 14: Predictive Perturbation

Schutz gegen ML-basierte Traffic-Correlation (RECTor):

- TrafficPredictor (Markov-Prototyp für Transformer)
- PredictivePerturbation (kontextbewusste Dummy-Injection)
- RateShaper (Token-Bucket)
- F1-Score: 0.9756 -> 0.0114 (98.8% Reduktion)
- Overhead: 0.07%

### Phase 15: Flow-Splitting

Schutz gegen Shape-basierte Flow-Correlation (Nym-Angriff):

- FlowSplitter: S=4 Gateways, Markov p=0.9
- CoverInjector: I=2.0 Multiplier
- FlowSplittingDefense (kombiniert)
- PR-AUC: 0.9998 -> 0.0699 (93% Reduktion)

### Phase 16: HS Introduction-Point Rotation

Schutz gegen Intersection-Angriffe (arXiv 2026):

- IntroPointManager mit 4 Rotations-Gründen
- Scheduled: 18-24h (randomisiert)
- Health: >=3 aufeinanderfolgende Fehler
- Age: >24h
- Intersection: gleicher Peer in N Sessions
- Exponential Backoff (2s -> 30s)
- Verhindert 52-Trial-Deanonymisierung

### Phase 17: Dynamic PoW

Schutz gegen IoT-Sybil-Angriffe (Kimwolf 2026):

- DynamicPoW: Difficulty skaliert mit Netzwerkgröße
- IPRateLimiter: 5/IP/Stunde, 20/Subnetz/Stunde
- Attack-Detection: >100 Versuche/Minute
- Reputation-Bypass: -1 Difficulty
- 100k IoT-Geräte werden blockiert

---

### Phase 18: TGTO (Website Fingerprinting Defense)

Schutz gegen Website Fingerprinting (FMWF, TGTO, Splash, FRUGAL):

- TemplateLibrary: 5 Templates (baseline/web/api/bulk/messaging)
- TraceMorpher: Resampling + Scaling
- SplashInjector: Kurze Perturbations-Bloecke
- WF-Genauigkeit: 96% -> 36% (60% Reduktion)
- FRUGAL: ASR 2.68% bei 30% Overhead

### Phase 19: Dandelion++ Enhancement

Schutz gegen Monero-Timing-Angriffe (OSPEAD):

- Poisson-Embargo: 2% -> 0.37% vorzeitiges Fluffing
- OSPEAD-Decoys: 1-in-4.2 -> ~1-in-16 MAP-Decoder
- Peer-Fallback: Verhindert stille Degradierung
- Cover-Txs: 10-20% Dummy-Transaktionen
- FCMP++-Ready: 100M+ Anonymitaets-Set

### Phase 20: HS-Obfuskation

Schutz gegen Hidden-Service-Fingerprinting (BurstToCell):

- BurstBreaker: Zerlegt lange Bursts (Threshold=5)
- SplashHS: Kurze Perturbations-Bloecke
- ResponsePadding: 128B Padding fuer HS-Antworten
- BurstToCell-Attn: 98.1% -> blockiert
- Break-Pad: TPR 76.84% bei 29% Overhead

### Phase 21: TCP-Normalisierung

Schutz gegen Header-Tagging (Rowland, Giffin, Patent):

- IPIDNormalizer: Randomisiert IP-ID
- TimestampScrubber: Untere Bits randomisiert
- WindowNormalizer: Standardwert
- OptionScrubber: Entfernt TCP-Optionen
- TLSRecordPadder: TLS-Record-Padding
- 12/12 kritische Luecken geschlossen

### Phase 22: 2-Hop Onion-Routing

Verschluesselter Tunnel mit doppelter Onion-Schicht:

- onion.py: X25519 + HKDF + ChaCha20-Poly1305 Layered Encryption
- tunnel.py: Frame-Typen FRAME_RELAY / FRAME_OPEN / FRAME_DATA
- _handle_relay baut zweiten Transport-Tunnel zum Nachbar-Peer
- _handle_exit entschluesselt Onion-Layer und verbindet zum Ziel
- proxy.py baut Doppel-Layer (Peer-2 innen, Peer-1 aussen)

### Phase 23: 3-Hop Onion-Routing + Padding

Dynamische Relay-Header und konstante Layer-Laengen:

- Padding auf 256-Byte-Bloecke (keine Ziel-Laengen-Leaks)
- pack_relay_header / unpack_relay_header mit dynamischem Ziel-Port
- PORT_TO_PEER_NAME Map fuer Multi-Peer-Identitaet
- proxy.py baut 3 verschachtelte Schichten
- 80 neue Unit-Tests (Onion-Basic, 3-Hop, Framing, Handshake)

Siehe [docs/ONION_ROUTING.md](docs/ONION_ROUTING.md) fuer Details.

### Phase 24: PQ-Transport-Handshake (Hybrid-KEM)

Transport-Handshake mit X25519 + ML-KEM-1024:

- 1665-Byte-Handshake-Frame (version || x_pub || mlkem_* || sig)
- Session-Key = HKDF(x25519_shared || mlkem_shared)
- Signatur ueber version || x_pub || mlkem_pub/ct
- Schutz gegen Harvest-Now-Decrypt-Later
- 20 neue Unit-Tests (Hybrid-Handshake + Tunnel-Handshake)
- Live-3-Hop-Test mit Hybrid-Handshake erfolgreich

Siehe [docs/PQ_CRYPTO.md](docs/PQ_CRYPTO.md) fuer Details.

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

380 Tests, alle gruen.

---

## Architektur

    src/erebos_network/
        router.py        # Routing-Entscheidungen
        sectors.py       # Adaptive Sektoren
        proxy.py         # Lokaler Proxy
        onion.py         # Onion-Routing-Schichten
        tunnel.py        # Erebos-Peer-Tunnel + Peer-Server
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
        hygiene.py       # Client-Hygiene
        hardening.py     # Memory-Hardening
        path_selection.py # Pfad-Auswahl
        e2e.py           # End-to-End Modus
        vrf_reputation.py # Verifizierbare Reputation
        hidden_service.py # Hidden Services
        obfuscation.py   # App-Obfuskation
        eclipse_protection.py # Eclipse-Schutz
        hs_hardening.py  # HS-Descriptor-Hardening
        reorg_protection.py # Monero-Reorg-Schutz
        augur_defense.py # Predictive Perturbation
        flow_splitting.py # Flow-Splitting
        hs_rotation.py   # HS-Introduction-Rotation
        dynamic_pow.py   # Dynamic Proof-of-Work
        tgto_defense.py  # TGTO (WF-Schutz)
        dandelion_plus.py # Dandelion++ Verstaerkung
        hs_obfuscation.py # HS-Obfuskation
        tcp_normalizer.py # TCP-Normalisierung
        crypto/
            pq_kem.py    # ML-KEM-1024
            pq_sig.py    # SLH-DSA-SHA2-256s
            threefish.py # Threefish-512
            hybrid.py    # Hybrid-Krypto
            hybrid_kem.py # X25519 + ML-KEM-1024
            pq_sphinx.py # PQ-Sphinx Mixnet-Format

---

## Dokumentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Technische Architektur
- [ONION_ROUTING.md](docs/ONION_ROUTING.md) - 3-Hop Onion-Routing
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
- [x] Phase 8: Security Hardening (Hybrid, Poisson, Cover)
- [x] Phase 9: Advanced Security (Hygiene, Hardening, Pfad, Sphinx)
- [x] Phase 10: Final Security (E2E, VRF, Hidden Services, Obfuskation)
- [x] Phase 11: Eclipse Protection (Subnetz-Diversity)
- [x] Phase 12: HS Descriptor Hardening (Anti-Flood)
- [x] Phase 13: Monero Reorg Protection (Anti-Reorg)
- [x] Phase 14: Predictive Perturbation (ML-Correlation)
- [x] Phase 15: Flow-Splitting (Shape-Analyse)
- [x] Phase 16: HS Introduction-Point Rotation (Intersection)
- [x] Phase 17: Dynamic PoW (IoT-Sybil)
- [x] Phase 18: TGTO (Website Fingerprinting)
- [x] Phase 19: Dandelion++ Enhancement (Monero-Timing)
- [x] Phase 20: HS-Obfuskation (HS-Fingerprinting)
- [x] Phase 21: TCP-Normalisierung (Header-Tagging)
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
