# Erebos Network

> **Ein neuartiges anonymes Netzwerk mit adaptiven Sektoren**

Erebos Network ist ein Forschungsprototyp für ein anonymes Netzwerk,
das Tor und I2P als Grundlage nutzt und um adaptive Sektoren erweitert.

## Was macht Erebos anders?

| Feature | Tor | I2P | Erebos |
|---------|-----|-----|--------|
| Onion-Routing | Ja | Nein | Ja |
| Garlic-Routing | Nein | Ja | Ja |
| Adaptive Hops | Nein | Nein | Ja |
| Mixnet | Nein | Nein | Bald |
| Payment | Nein | Nein | Bald |

## Adaptive Sektoren

| Sektor | Hops | Anonymität | Latenz | Nutzung |
|--------|------|------------|--------|---------|
| Schnell | 2 | Mittel | 300ms | Surfen |
| Standard | 3 | Hoch | 800ms | Alltag |
| Hoch | 5 | Sehr hoch | 2s | Sensibel |
| Mixnet | 7 | Maximal | 5s | Extrem |

## Installation

    cd ~/Documents/GitHub/erebos-network
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

## Verwendung

Demo ausführen:

    python -m erebos_network --demo

Tests ausführen:

    pytest

## Architektur

    src/erebos_network/
        __init__.py       # Package
        __main__.py       # CLI
        sectors.py        # Adaptive Sektoren
        router.py         # Routing-Entscheidungen
        proxy.py          # Lokaler Proxy

## Roadmap

- [x] Phase 1: Router + Sektoren
- [ ] Phase 2: Mixnet-Layer
- [ ] Phase 3: Erebos-Peer-Discovery
- [ ] Phase 4: Dezentrale Governance
- [ ] Phase 5: Monero-Payment

## Lizenz

MPL 2.0 - siehe LICENSE
