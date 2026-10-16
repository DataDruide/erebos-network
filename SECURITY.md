# Sicherheit in Erebos Network

Dieses Dokument beschreibt das Bedrohungsmodell, die implementierten
Verteidigungsebenen und die **bekannten Grenzen** des Erebos-Network-Stacks.
Es ist ehrlich gemeint: was hier nicht steht, ist nicht geschützt.

Stand: 2026-10-16 · Version `v0.3.2-topic1c-adaptive-cover`

---

## 1. Zweck und Umfang

Erebos ist ein Browser für das I2P-Netzwerk mit zusätzlicher
Verkehrs-Härtung auf der Client-Seite. Dieses Dokument deckt ab:

- Netzwerk-Härtung des **Erebos-Network-Daemons** (`erebos-network`)
- **API-Schicht** (`api.py`) — HTTP-Endpoints für die Browser-UI
- **Peer-Transport** (`tunnel.py`, `proxy.py`, `onion.py`)
- **Cover-Traffic** (`cover.py`)

Nicht abgedeckt:

- I2P-Protokoll selbst (das macht i2pd)
- Browser-Engine-Härtung (Firefox ESR 128, Mullvad-Basis)
- Kryptographische Primitive (nutzen wir aus `liboqs`, `cryptography`)

---

## 2. Bedrohungsmodell

### Angreifer-Klassen

| Klasse | Fähigkeiten | Adressiert? |
|---|---|---|
| **Passiver Netzwerk-Beobachter** | sieht Paketgrößen, Timing, Frequenz | ✅ teilweise |
| **Aktiver Netzwerk-Angreifer** | kann Frames modifizieren/verwerfen | ✅ durch AEAD |
| **Kompromittierter Peer** | ein Hop im Onion-Pfad | ❌ außerhalb Modell |
| **Hoster-Konzentration** | viele Peers bei einem Anbieter | ⚠️ Monitoring fehlt |
| **Lokaler Angreifer** | kann Daemon-Prozess lesen | ❌ außerhalb Modell |

### Was ein passiver Beobachter sehen kann

- Paketgrößen auf der Leitung
- Timing zwischen Frames
- Richtung (Uplink / Downlink)
- Anzahl der Verbindungen
- TLS-Fingerprint des Transports

### Was er *nicht* sehen kann

- Klartext-Payload (ChaCha20Poly1305)
- Session-Keys (X25519 + ML-KEM-1024)
- Ziel-Host hinter 3-Hop-Onion (bei korrektem Pfad)

---

## 3. Implementierte Verteidigungsebenen

### P0.2 — Hybrid-Post-Quanten-Schlüsselaustausch

- **Algorithmus:** X25519 + ML-KEM-1024 (NIST Level 5)
- **KDF:** HKDF-SHA256 (RFC 5869)
- **Signatur:** Ed25519 (Handshake-Bindung)
- **Warum hybrid:** Solange X25519 *oder* ML-KEM-1024 ungebrochen ist,
  bleibt der Session-Key sicher — auch gegen zukünftige Quantencomputer.
- **Modul:** `src/erebos_network/crypto/hybrid_kem.py`
- **Verifikation:** `GET /api/network/pqc-status`

### P1.1a — API-Padding + Jitter

- **Padding:** Bucket-Größen von 256 Byte; Antworten werden auf die
  nächste Bucket-Grenze aufgefüllt (Whitespace-Padding innerhalb JSON)
- **Jitter:** 0–30 ms uniform pro Antwort
- **Header:** `X-Erebos-Original-Size`, `X-Erebos-Padded-Size`
- **Zweck:** erschwert Größen- und Timing-Fingerprinting auf API-Ebene
- **Modul:** `src/erebos_network/padding.py`, `delay.py`

### P1.1b — Echter Cover-Traffic auf Peer-Kanal

- **Frame-Typ:** `FRAME_COVER = 0x04`
- **Modus:** Burst (3 Frames à 256–1024 Byte in 20 ms, dann 2 s Pause)
- **Wirkung:** jede aktive SOCKS5-Verbindung sendet konstanten
  Uplink-Cover — ein Beobachter sieht keine „Stille" bei Inaktivität
- **Empfänger:** erkennt `FRAME_COVER`, verwirft Payload, antwortet nicht
- **Modul:** `src/erebos_network/cover.py` (`TunnelCoverInjector`)

### P4a — Downlink-Bucket-Padding (seit `v0.3.8`)

- **Idee:** Jeder Frame im Peer-Transport (Handshake, Uplink, Downlink)
  wird auf 256-Byte-Buckets genormt.
- **Format:** `[2B padding_len (BE)][original data][random padding]`
- **Default:** Padding ist **an** (Blockgroesse 256). Deaktivierbar per
  `EREBOS_PADDING_BLOCK=0` in der Umgebung.
- **Wirkung:** Ein Beobachter sieht keine Frame-Groessen-Varianz mehr.
  Die Groessen-Seite des Shape-Signals ist eliminiert.
- **Was nicht passiert:** Kein zusaetzlicher Timing-Jitter, kein Cover.
  Die Anzahl und der Zeitpunkt der Frames bleiben sichtbar.
- **Modul:** `src/erebos_network/tunnel.py` (`_apply_padding`/`_strip_padding`)

### P1.3 — Reactive Drop-Cover (seit `v0.3.7`)

- **Idee:** Zusaetzlich zum regulaeren Cover sendet der Injector einen
  kurzen Frame-Burst, wenn Downlink-Traffic ankommt.
- **Mechanik:** `notify_downlink(size)` sammelt eingehende Frames in
  einem Sliding Window (Default 100 ms). Der Loop spiegelt die Anzahl
  (max `reactive_max_match`) und die Durchschnittsgroesse (+/- Jitter).
- **Grund:** Nym-Lehre — die Asymmetrie zwischen Uplink- und
  Downlink-Form ist selbst ein Korrelations-Signal. Wer beide Seiten
  sieht, erkennt "Client empfaengt, sendet aber nicht".
- **Wirkung:** Ein Beobachter sieht auf beiden Seiten gleichmaessiges
  Rauschen — die Formkorrelation sinkt.
- **Modul:** `src/erebos_network/cover.py` (`_send_reactive_burst`)

### P1.2 — Adaptiver Cover-Traffic

- **Drei Phasen:** `normal` (100 %), `quiet` (20 %), `boost` (200 %)
- **Quiet-Phase:** nach echtem Traffic für 3 s — drosselt, **nie auf null**
  (sonst wäre „Traffic = Stille" selbst ein Fingerprint)
- **Boost-Phase:** nach > 10 s Idle — maximal 2×, höher wäre erkennbar
- **Modul:** `src/erebos_network/cover.py` (`_effective_rate()`)

---

## 4. Bekannte Grenzen

Diese Liste ist wichtiger als die Verteidigungsliste. Was hier nicht steht,
ist **nicht** geschützt.

### Netzwerk

- **Cover-Traffic ist unidirektional.** Der Empfänger antwortet nicht.
  Ein Beobachter, der *beide* Seiten sieht, erkennt die Asymmetrie.
- **Burst-Parameter sind nicht empirisch kalibriert.** 3×20 ms/2 s ist
  ein plausibler Default, aber nicht aus echten HTTP-Bursts abgeleitet.
  Die Nym-Forschung zeigt: Cover-Traffic wirkt gegen Website-Fingerprinting
  nur, wenn die Burst-Struktur echter Web-Requests nahekommt.
- **Kein aktives Netzwerk-Peering im Daemon.** Der Daemon öffnet keine
  Peer-Verbindungen von selbst. Der 3-Hop-Onion-Pfad wird nur vom
  SOCKS5-Proxy aufgebaut, wenn der Browser Traffic sendet. Im Idle-Zustand
  gibt es **keinen** Cover-Traffic zwischen Peers.
- **Hoster-Konzentrations-Monitoring fehlt.** Wenn viele Peers bei
  einem Anbieter liegen, ist der Anonymitäts-Gewinn reduziert. Wir messen
  das aktuell nicht.

### Kryptographie

- **Keine formale Verifikation** der Krypto-Pfade. Die Tests prüfen
  Roundtrips, nicht die Sicherheit der Konstruktionen.
- **Schlüssel-Speicherung:** Private Keys liegen unverschlüsselt unter
  `KEYS_DIR`. Ein lokaler Angreifer mit Lesezugriff hat vollen Zugriff.
- **Kein Key-Rotation-Mechanismus** für langfristige Peer-Identitäten.

### API

- **Client entpaddet seit `v0.2.1`.** Die Browser-UI liest den
  `X-Erebos-Original-Size`-Header und schneidet den Body vor `JSON.parse`.
  Fallback auf vollen Text, falls der Header fehlt (aeltere Daemon-Version).
- **API-Endpoints haben kein Rate-Limiting.** Ein lokaler Angreifer kann
  den Daemon mit Anfragen fluten.

### Browser

- **Engine unverändert.** Wir nutzen Firefox ESR 128 mit
  `resistFingerprinting`-Konfiguration, aber **ohne eigene Engine-Patches**.
  Bekannte CVE-Muster (z. B. `indexedDB.databases()`-Lecks) sind nur
  durch Upstream-Patches adressiert.
- **Kein JavaScript-Default-Off.** Die UI lädt Skripte per Default.

---

## 5. Angriffe — adressiert vs. nicht adressiert

| Angriff | Status | Maßnahme / Grund |
|---|---|---|
| Größen-Fingerprinting (API) | ✅ erschwert | Bucket-Padding |
| Timing-Fingerprinting (API) | ✅ erschwert | 0–30 ms Jitter |
| Timing-Fingerprinting (Netz) | ✅ erschwert | Cover-Traffic |
| Website-Fingerprinting | ⚠️ teilweise | Cover unkalibriert |
| Flow-Korrelation | ❌ nicht adressiert | kein Mixnet-Delay im Daemon |
| Quantencomputer (Retro) | ✅ geschützt | Hybrid-PQC |
| Frame-Modifikation | ✅ geschützt | ChaCha20Poly1305 |
| Kompromittierter Hop | ❌ außerhalb Modell | Onion schützt nicht gegen bösartige Peers |
| Lokaler Angreifer | ❌ außerhalb Modell | Daemon hat keine Hardening-Maßnahmen |

---

## 6. Verifikation

- **Test-Abdeckung:** 664 Tests, alle grün (Stand 2026-10-16)
- **Kritische Pfade:**
  - `tests/test_hybrid_kem_hardening.py` — PQC-Handshake
  - `tests/test_traffic_integration.py` — API-Padding + Jitter
  - `tests/test_cover_injection.py` — `FRAME_COVER`-Mechanik
  - `tests/test_adaptive_cover.py` — Quiet/Boost-Phasen
- **Reproduzierbare Builds:** implementiert seit `v0.3.4-reproducible-builds`.
  `make verify` baut das Wheel zweimal und vergleicht die Inhalts-Hashes.
  Einschränkung: `liboqs-python` lädt die liboqs-C-Bibliothek zur Laufzeit
  nach — bei unterschiedlichen liboqs-Systemversionen kann das Wheel
  abweichen. Reproduzierbarkeit ist für die Python-Ebene garantiert.

### Was ein externer Audit prüfen müsste

1. **Krypto-Implementierung:** HKDF-Konstruktion, ML-KEM-Bindung,
   Domänentrennung der Signaturen
2. **Cover-Traffic-Kalibrierung:** Sind die Burst-Parameter gegen
   echte Traffic-Profile getestet?
3. **Empfänger-Verhalten:** Ist `FRAME_COVER`-Discard wirklich
   konstant (Timing-seitig)?
4. **API-Angriffsfläche:** Padding-Header als Information-Leak?
5. **Schlüssel-Speicherung:** Sind `KEYS_DIR`-Berechtigungen korrekt?

---

## 7. Melden von Sicherheitsproblemen

Sicherheitslücken bitte **nicht** über öffentliche GitHub-Issues melden.
Stattdessen: E-Mail an den Maintainer (siehe Repo-Profil).

Wir bemühen uns um Antwort innerhalb von 72 Stunden. Für bestätigte
Schwachstellen gibt es keine monetäre Belohnung — dies ist ein
Forschungsprojekt, kein kommerzielles Produkt.

---

## 8. Referenzen

- **NIST SP 800-227** — Recommendations for Key-Encapsulation Mechanisms
- **Signal PQXDH** — Post-Quantum Extended Diffie-Hellman (Vorlage)
- **Nym PETS-Studie** — Cover-Traffic-Effektivität gegen Website-Fingerprinting
- **Tor Proposal #269** — Hybrid Handshakes (NTRU Prime)
- **F-Droid Reproducible Builds Study** — Verifikations-Hürden
- **Mullvad Browser** — Uniformität statt Randomisierung beim Fingerprinting

---

## 9. Changelog

| Version | Datum | Änderung |
|---|---|---|
| `v0.3.0-topic1-integration` | 2026-10-16 | API-Padding + Jitter, PQC-Endpoint |
| `v0.3.1-topic1b-cover-injection` | 2026-10-16 | `FRAME_COVER` + Burst-Modus |
| `v0.3.2-topic1c-adaptive-cover` | 2026-10-16 | Quiet/Boost-Phasen |
| `v0.3.3-security-doc` | 2026-10-16 | SECURITY.md mit Bedrohungsmodell |
| `v0.3.4-reproducible-builds` | 2026-10-16 | `make verify` + requirements.lock |
| `v0.2.1-client-unpadding` (browser) | 2026-10-16 | Client entpaddet API-Antworten |
