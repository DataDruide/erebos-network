# Erebos Network - Architektur

Version: 1.0
Status: Prototyp

## Uebersicht

Erebos ist ein mehrschichtiges anonymes Netzwerk.

    Browser (about:erebos)
        HTTP-API
    API-Schicht (api.py)
    Routing-Schicht (router.py)
    Mixnet-Schicht (mixnet.py)
    Krypto-Schicht (crypto/)
    Transport-Schicht (Tor/I2P/Peer)

## Schichten

### 1. Transport-Schicht

- Tor (SOCKS5 auf 127.0.0.1:9050) fuer Clearnet
- I2P (HTTP-Proxy auf 127.0.0.1:4444) fuer eepSites
- Erebos-Peer (direkt) fuer Peer-zu-Peer

### 2. Krypto-Schicht

| Algorithmus | Zweck | Sicherheit |
|-------------|-------|------------|
| ML-KEM-1024 | Schluesselaustausch | NIST Level 5 |
| SLH-DSA-SHA2-256s | Signaturen | NIST Level 5 |
| Threefish-512 | Symmetrisch | 256-Bit PQ |

### 3. Mixnet-Schicht

- Padding - alle Nachrichten auf 1024B
- Delay - zufaellige Verzoegerungen (0-500ms)
- Batching - Gruppen von 10 Nachrichten
- Cover - Dummy-Traffic (0.5-2.0/s)

### 4. Routing-Schicht

| Sektor | Hops | Anonymitaet | Latenz |
|--------|------|-------------|--------|
| fast | 2 | 4/10 | 300ms |
| standard | 3 | 7/10 | 800ms |
| high | 5 | 9/10 | 2s |
| mixnet | 7 | 10/10 | 5s |

### 5. API-Schicht

- GET /status
- GET /route?target=X&sector=Y
- GET /resolve?name=X
- GET /stats

## Datenfluss

1. Browser sendet Anfrage an /route
2. API ruft router.route() auf
3. Router klassifiziert Ziel (Clearnet/eepSite/Peer)
4. Router waehlt Sektor
5. Mixnet wendet Padding + Delay an
6. Krypto verschluesselt mit ML-KEM + Threefish
7. Transport sendet ueber Tor/I2P/Peer
8. Antwort zurueck an Browser

## Module

| Modul | Zweck |
|-------|-------|
| router.py | Routing-Entscheidungen |
| sectors.py | Adaptive Sektoren |
| proxy.py | Lokaler Proxy |
| mixnet.py | Mixnet-Layer |
| padding.py | Padding |
| delay.py | Verzoegerungen |
| batching.py | Batching |
| cover.py | Cover-Traffic |
| dht.py | Kademlia-DHT |
| discovery.py | Peer-Discovery |
| naming.py | .erebos-Naming |
| peer.py | ErebosPeer |
| pow.py | Proof-of-Work |
| reputation.py | Reputation |
| consensus.py | Konsens |
| governance.py | Governance |
| wallet.py | Monero-Wallet |
| payment.py | Payment |
| swap.py | Atomic Swaps |
| api.py | HTTP-API |
| hygiene.py | Client-Hygiene |
| hardening.py | Memory-Hardening |
| path_selection.py | Pfad-Auswahl |
| e2e.py | End-to-End Modus |
| vrf_reputation.py | Verifizierbare Reputation |
| hidden_service.py | Hidden Services |
| obfuscation.py | App-Obfuskation |
| eclipse_protection.py | Eclipse-Schutz |
| hs_hardening.py | HS-Descriptor-Hardening |
| reorg_protection.py | Monero-Reorg-Schutz |
| augur_defense.py | Predictive Perturbation |
| flow_splitting.py | Flow-Splitting |
| hs_rotation.py | HS-Intro-Point-Rotation |
| dynamic_pow.py | Dynamic Proof-of-Work |
| crypto/pq_kem.py | ML-KEM-1024 |
| crypto/pq_sig.py | SLH-DSA |
| crypto/threefish.py | Threefish-512 |
| crypto/hybrid.py | Hybrid |
| crypto/hybrid_kem.py | X25519 + ML-KEM-1024 |
| crypto/pq_sphinx.py | PQ-Sphinx |

304 Tests insgesamt.
