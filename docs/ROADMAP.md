# Erebos Network - Roadmap

Status: 7 Phasen komplett

## Abgeschlossen

### Phase 1: Router + Adaptive Sektoren
- Router mit Clearnet/eepSite/Peer-Klassifikation
- 4 adaptive Sektoren (fast, standard, high, mixnet)
- 16 Tests

### Phase 2: Mixnet-Layer
- Padding auf 1024B
- Delay (uniform/exponential/normal)
- Batching
- Cover-Traffic
- 23 Tests

### Phase 3: DHT + Discovery + Naming
- Kademlia-DHT (256-Bit Keys)
- Peer-Discovery
- .erebos-Naming
- 27 Tests

### Phase 4: Dezentrale Governance
- Proof-of-Work
- Reputation
- Konsens
- 28 Tests

### Phase 5: Monero-Payment
- Wallet (Simulation)
- Payment-System
- Atomic Swaps
- 30 Tests

### Phase 6: HTTP-API + Browser-Integration
- API-Server (/status, /route, /resolve, /stats)
- Browser-UI (about:erebos)
- 6 Tests

### Phase 7: Post-Quanten-Krypto
- ML-KEM-1024 (NIST Level 5)
- SLH-DSA-SHA2-256s
- Threefish-512
- 6 Tests

### Phase 8: Security Hardening
- Hybrid-KEM (X25519 + ML-KEM-1024)
- Poisson-Mixing
- Konstanter Cover-Traffic
- 11 Tests

### Phase 9: Advanced Security
- Client-Hygiene
- Memory-Hardening
- Pfad-Auswahl (4 Strategien)
- PQ-Sphinx
- 17 Tests

### Phase 10: Final Security
- End-to-End (kein Exit noetig)
- VRF-Reputation (Anti-Framing)
- Hidden Services (.erebos)
- App-Obfuskation
- 20 Tests

Gesamt: 184 Tests.

## In Arbeit

### Phase 8: Paper schreiben
- [ ] Abstract
- [ ] Introduction
- [ ] Related Work
- [ ] Design
- [ ] Evaluation
- [ ] Conclusion
- [ ] arXiv-Submission

### Phase 9: Community aufbauen
- [ ] GitHub Discussions
- [ ] Reddit-Post
- [ ] Hacker News
- [ ] I2P-Forum

### Phase 10: Netzwerk-Deployment
- [ ] Bootstrap-Nodes
- [ ] Monitoring
- [ ] Erste Peers

## Zukuenftige Phasen

### Phase 11: Erster Build
- [ ] mach bootstrap
- [ ] mach build
- [ ] Release v0.1

### Phase 12: Echte Monero-Integration
- [ ] monero-wallet-rpc
- [ ] Echte Transaktionen

### Phase 13: Bridges
- [ ] Tor-Bridges
- [ ] Obfs4, meek, snowflake

### Phase 14: Mobile Apps
- [ ] Android
- [ ] iOS
