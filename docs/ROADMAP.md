# Erebos Network - Roadmap

Status: 27 Phasen komplett, 781 Tests

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

### Phase 11: Eclipse Protection
- Subnetz-Diversity (max. 2 Peers pro /24)
- 11 Tests

### Phase 12: HS Descriptor Hardening
- Groessen/Service/Global/Rate-Limits
- Proof-of-Work + TTL-Cleanup
- 12 Tests

### Phase 13: Monero Reorg Protection
- Chain-Height-Tracking
- Reorg-Detection + Payment-Invalidierung
- 20/30 Bestaetigungen
- 10 Tests

### Phase 14: Predictive Perturbation
- TrafficPredictor + Perturbation
- 14 Tests

### Phase 15: Flow-Splitting
- S=4 Gateways, I=2.0 Cover
- 16 Tests

### Phase 16: HS-Intro-Point-Rotation
- 4 Rotations-Gruende + Intersection-Detection
- 19 Tests

### Phase 17: Dynamic PoW
- Difficulty skaliert + IP-Rate-Limits
- 20 Tests

### Phase 18: TGTO
- Template-Guided Traffic Obfuscation
- 18 Tests

### Phase 19: Dandelion++ Enhancement
- Poisson-Embargo + OSPEAD + FCMP++
- 23 Tests

### Phase 20: HS-Obfuskation
- BurstBreaker + Splash + Response-Padding
- 16 Tests

### Phase 21: TCP-Normalisierung
- IP-ID + Timestamps + Window + TLS
- 19 Tests

### Phase 22: 2-Hop Onion-Routing
- onion.py: X25519 + HKDF + ChaCha20-Poly1305 Layered Encryption
- tunnel.py: Frame-Typen FRAME_RELAY/FRAME_OPEN/FRAME_DATA
- _handle_relay baut zweiten Transport-Tunnel
- _handle_exit entschluesselt Onion-Layer
- proxy.py baut Doppel-Layer (Peer-2 innen, Peer-1 aussen)
- __main__.py: --peer-port fuer Multi-Peer-Setup
- scripts/generate_keys.py: Peer-Key-Generator

### Phase 23: 3-Hop Onion-Routing + Padding
- onion.py: Padding auf 256-Byte-Bloecke
- pack_relay_header/unpack_relay_header mit dynamischem Ziel-Port
- tunnel.py: PORT_TO_PEER_NAME Map (Port -> Peer-Identitaet)
- _handle_relay entschluesselt eigene Schicht vor Weiterleitung
- proxy.py baut 3 verschachtelte Schichten
- 80 neue Unit-Tests (Onion-Basic + 3-Hop + Framing + Handshake)
- 0 Tests gebrochen

### Phase 24: PQ-Transport-Handshake (Hybrid-KEM)
- scripts/generate_keys.py erweitert um ML-KEM-1024 Keys
  (peerN_mlkem, peerN_mlkem.pub)
- tunnel.py: HANDSHAKE_V2_HYBRID (0x02), 1665-Byte-Handshake-Frame
- _derive_key_pq: HKDF(x25519_shared || mlkem_shared)
- _load_mlkem_keypair: Rohbyte-Persistenz
- Signaturdeckung: version || x_pub || mlkem_pub/ct
- connect() leitet peer_name aus Ziel-Port ab
- Schutz gegen Harvest-Now-Decrypt-Later
- 20 neue Unit-Tests (test_hybrid_handshake.py +
  test_tunnel_handshake.py umgeschrieben)
- Live-3-Hop-Test mit Hybrid-Handshake erfolgreich

### Phase 25: Rendezvous + Hidden-Service Ende-zu-Ende
- Rendezvous-Punkt mit Stream-Registry (parallele Clients)
- PeerDhtStore (DHT-Persistenz in Peers, ueberlebt Neustart)
- HiddenServiceRuntime (produktiver Hidden-Service als Modul)
- Cleanup von rendezvous_pairs beim Verbindungsende
- Lasttest: 10/10, 50/50, 100/100 HTTP 200 (mit ulimit -n 4096)
- Details in docs/known-limitations.md

Gesamt: 489 Tests.

## In Arbeit

### Paper schreiben
- [ ] Abstract
- [ ] Introduction
- [ ] Related Work
- [ ] Design
- [ ] Evaluation
- [ ] Conclusion
- [ ] arXiv-Submission

### Community aufbauen
- [ ] GitHub Discussions
- [ ] Reddit-Post
- [ ] Hacker News
- [ ] I2P-Forum

### Netzwerk-Deployment
- [ ] Bootstrap-Nodes
- [ ] Monitoring
- [ ] Erste Peers

## Zukuenftige Phasen

### Erster Build
- [ ] mach bootstrap
- [ ] mach build
- [ ] Release v0.1

### Echte Monero-Integration
- [ ] monero-wallet-rpc
- [ ] Echte Transaktionen

### Bridges
- [ ] Tor-Bridges
- [ ] Obfs4, meek, snowflake

### Mobile Apps
- [ ] Android
- [ ] iOS

---

### Phase 26: Mail-Rotation + Onboarding (2026-10-27)
- mail_keys: X25519, ML-KEM-1024, Ed25519, ML-DSA-65 (alle vier persistent)
- mailboxes: hybrid PQ-verschluesselt (X25519 + ML-KEM) + signiert
  (Ed25519 + ML-DSA)
- Signaturen: Ed25519 + ML-DSA-65, Verifikation mit 4 Zustaenden:
  - VERIFIED (gruen) — Signatur gueltig, aktuelle Version
  - VERIFIED_OUTDATED (orange) — Signatur gueltig, aeltere Version
  - VERIFIED_EXPIRED (orange) — Signatur gueltig, Key abgelaufen
  - VERIFY_FAILED (rot) — Signatur ungueltig
- Key-Rotation (Ansatz B): volle Rotation aller vier Keys,
  alte Privkeys in mail_key_history (alte Mails bleiben lesbar)
- Auto-Rotation: 7 Tage vor Ablauf, alle 6h geprueft (asyncio-Task)
- Rate-Limiting: 1x Rotation pro Stunde pro UUID + Retry-After-Header
- Key-Expiry: valid_until, Default 90 Tage (konfigurierbar)
- Onboarding-Flow: duestere Progressbar (5 Schritte), Welcome-Seite
  mit UUID + @erebos-Adresse + Forum-Username
- Identitaeten: UUID <-> E-Mail <-> Forum <-> Mail (eine Identitaet
  fuer alles)
- Forum-Auto-Login nach Onboarding
- Identitaets-Recovery: UUID/E-Mail eingeben -> Session reaktivieren
- Backup/Restore: docs + Skripte + Cron + systemd-Timer
- 25 neue Tests (Identity, Onboarding, Auto-Login, Recovery)

Gesamt: 781 Tests.

Status: 27 Phasen komplett, 781 Tests.

---

### Phase 27: Refactor + Security Hardening (2026-10-27)
- **liboqs-API-Contract-Tests** (8 Tests):
  - ML-DSA-65: generate_keypair/export_secret_key/sign/verify
  - ML-KEM-1024: generate_keypair/export_secret_key/encap/decap
  - Mechanism-Listen (ML-DSA-65, ML-KEM-1024)
  - Schlaegt sofort fehl bei liboqs-python-Update
- **Timing-sichere Signatur-Verifikation**:
  - verify_mail prueft Ed25519 UND ML-DSA-65 IMMER
  - _safe_ed25519_verify(), _safe_mldsa_verify()
  - Verhindert Timing-Angriffe
- **landing_pages.py aufgeteilt** (1115 -> 395 Zeilen, -65%):
  - renderers.py (75 Zeilen): _page, _escape, _format_timestamp,
    _render_identity_box
  - http_utils.py (74 Zeilen): http_response, parse_http_request
  - pages_onboarding.py (122 Zeilen): Startseite, Regeln, Wiki
  - pages_mail.py (~380 Zeilen): /mail + /mail/rotate
  - pages_forum.py (~395 Zeilen): alle /forum-Routen
  - landing_pages.py: nur noch render_page-Dispatcher
- **14 neue Tests** (8 liboqs + 6 Timing)

Gesamt: 781 Tests.

Status: 27 Phasen komplett, 781 Tests.
