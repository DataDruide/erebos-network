# Bekannte Limitierungen

Stand: Nach Kademlia-DHT (Punkt A) und Multi-Intro-Point-Rotation (Punkt B2)

## Was funktioniert

| Feature | Status |
|---|---|
| Erebos-Tunnel Ende-zu-Ende (HTTP ueber SOCKS5) | ✅ funktioniert |
| Hybrid-Krypto (ML-KEM + X25519 + Ed25519) | ✅ funktioniert |
| Rendezvous-Punkt mit mehreren parallelen Clients | ✅ funktioniert |
| Parallele Verbindungen (10/50/100 gleichzeitig) | ✅ 100/100 mit `ulimit -n 4096` |
| **Ende-zu-Ende-Verschluesselung (E2E)** | ✅ peer1 sieht keinen HTTP-Klartext |
| DHT-Persistenz in Peers | ✅ Descriptor ueberlebt Neustart |
| **Kademlia-DHT (verteilt)** | ✅ Descriptor ueberlebt Peer-Neustart |
| Hidden-Service-Reconnect | ✅ Exponential Backoff |
| **Multi-Intro-Point-Rotation** | ✅ Health-Check + Rotation |
| Hidden-Service-Schluessel persistent | ✅ stabile `.erebos`-Adresse |
| `conn_id`-Reset | ✅ kein Stream-ID-Overflow |
| Produktiver Hidden-Service (`HiddenServiceRuntime`) | ✅ funktioniert |

## Offene Limitierungen

### 1. Parallele Verbindungen > 100 brauchen `ulimit -n 4096`

Bei 100 parallelen Verbindungen braucht der Prozess ~500 Datei-
Deskriptoren. macOS-Standard ist `ulimit -n 256`, was zu ~19/100
Fehlschlaegen fuehrt.

**Empfehlung**: `ulimit -n 4096` vor dem Start.

### 2. Intro-Rotation waehlt ggf. nicht-erreichbare Ersatz-Peers

`_rotate_intro_point` waehlt den naechsten Peer aus `_known_peers`
(peer4, peer5), auch wenn dieser nicht laeuft. In einem echten
Netzwerk wuerden mehr Peers laufen; im Test-Pool (3 Peers) ist
peer4/peer5 nicht gestartet.

**Loesung (offen)**: `_rotate_intro_point` sollte nur **erreichbare**
Ersatz-Peers waehlen (Health-Check vor Rotation).

### 3. Onion-Layer fuer mehrere Hops fehlt

Aktuell: **ein** Rendezvous-Punkt. Echte Anonymitaet gegen den
Rendezvous-Punkt erfordert **mehrere** Hops (Onion-Routing).

**Loesung (offen)**: Onion-Layer zwischen Client und Hidden-Service,
mit 2-3 Rendezvous-Punkten.

### 4. Echte verteilte Kademlia-DHT: Bootstrap-Reihenfolge

Die Peers bootstrappen sich gegenseitig, aber wenn **alle** Peers
gleichzeitig starten, gibt es Timeouts (Retry mit Backoff ist
implementiert). In einem echten Netzwerk mit stabilen Peers ist
das kein Problem.

## Docker-Betrieb (Stand nach Migration)

### 5. Hidden-Service-Schluessel nicht ueber Container-Neustart persistent

`HiddenServiceRuntime` speichert den Ed25519-Schluessel in
`/root/.erebos/hs_key_<bind_port>.pem` **im Container**. Bei
`docker-compose up --force-recreate` (oder `down`/`up`) ist der
Schluessel weg -> neue `.erebos`-Adresse. Clients, die die alte
Adresse gecacht haben, finden den Dienst nicht mehr.

**Loesung (offen)**: Volume-Mount in `docker-compose.yml`:

    hidden-service:
      volumes:
        - hs-keys:/root/.erebos
    volumes:
      hs-keys:

### 6. 3-Hop-Rendezvous-Kette hat festen Pfad (pragmatisch geloest: 2-Hop-Fallback)

Der Proxy baut den Onion-Pfad fix als `proxy -> peer2 -> peer3 -> peer1`.
Faellt peer3 aus, bricht die Kette (mit 5s-Timeout seit dem letzten
Patch, aber ohne Fallback auf einen alternativen Pfad).

**Pragmatisch geloest**: Faellt peer3 aus, baut der Proxy einen
2-Hop-Onion (peer2 -> peer1) als Fallback. Der Standard-Pfad
bleibt peer2 -> peer3 -> peer1. Im Test: peer3 gestoppt ->
HTTP 200 in 6.3s (statt Fehler).

**Weiterhin offen**: peer2-Ausfall ist nicht abgedeckt (peer2
ist der erste Hop). Fuer vollstaendige Pfadwahl muesste der
Proxy eine Liste von Pfaden probieren (Hilfsfunktion
_try_onion_path). Erfordert, dass der
Rendezvous-Punkt mehrere Paare pro Key verwalten kann (was er
bereits tut: `rendezvous_pairs[key]["clients"]` ist eine Liste).

### 7. `--dht-peers` im Hidden-Service: Format beachten

Seit dem letzten Patch akzeptiert `--dht-peers` sowohl reine Ports
(int, dann wird `rendezvous_host` genutzt) als auch `host:port`-
Strings. In Docker muss die `host:port`-Form genutzt werden, damit
der Descriptor an alle Peers verteilt wird:

    --dht-peers 172.20.0.10:9999,172.20.0.11:9998,172.20.0.12:9997

Mit reinen Ports landet der Descriptor nur bei `rendezvous_host`
(typisch peer1) — dann ist er bei peer1-Ausfall nicht mehr
auffindbar.

### 8. Admin-Token `changeme` ist Platzhalter (geloest: .env)

Das Forum-Admin-Token wird in `docker-compose.yml` als
`EREBOS_FORUM_ADMIN_TOKEN=changeme` gesetzt. Das ist ein
**Platzhalter** — jeder, der die Doku liest, kennt ihn.

**Loesung (offen fuer Produktion)**: Zufaelliges Token setzen
(z.B. `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`)
in einer `.env`-Datei (nicht im Repo) und in `docker-compose.yml`
per `${EREBOS_FORUM_ADMIN_TOKEN}` referenzieren.

### 9. Rate-Limit ist global, nicht pro Client (geloest: Cookie)

Der Hidden Service sieht die Client-IP **nicht** (der Proxy reicht
nur den HTTP-Request durch). Deshalb zaehlt das Rate-Limit global:
10 neue Threads / 30 Antworten pro 10 Minuten im **gesamten** Forum.
Ein einzelner Spammer kann das Limit fuer alle erreichen.

**Loesung (offen)**: Client-Identitaet durch den Proxy (z.B. ein
signiertes Client-Token, das der Proxy setzt). Erfordert Aenderungen
am Proxy-Protokoll.

### 10. Kein Editieren von Posts (nur Loeschen) (geloest: edit_post)

Moderation kann Threads und Posts **loeschen**, aber nicht
editieren. Ein Tippfehler im Eroeffnungsbeitrag erfordert
Loeschen + Neuerstellen.

**Loesung (offen)**: Editier-Formular mit vorausgefuelltem Inhalt,
POST /forum/<id>/post/<idx>/edit.

### 11. Kein Thread-uebergreifendes Loeschen aller Posts eines Autors (geloest)

Moderation arbeitet pro Thread/Post. Um alle Beitraege eines
Autors zu entfernen, muss jeder Thread einzeln geoeffnet werden.

**Loesung (offen)**: Admin-Seite mit Autoren-Liste und
"Alle Posts von <Autor> loeschen".

### 12. Kein HTTPS (nur ueber Erebos-Proxy sicher)

Der Hidden Service spricht HTTP, nicht HTTPS. Innerhalb des
Erebos-Tunnels ist der Traffic durch die E2E-Verschluesselung
(ChaCha20-Poly1305) geschuetzt. Aber: Wer den Hidden Service
direkt erreicht (ohne Erebos-Proxy), sieht Passwoerter und
Session-Cookies im Klartext.

**Loesung (offen)**: TLS im HTTP-Backend, oder ein Hinweis
auf der Startseite: "Nur ueber den Erebos-Proxy nutzen."

### 13. Session-Cookie ohne `Secure`-Flag

Das Session-Cookie (`forum_session`) wird mit `HttpOnly` und
`SameSite=Lax` gesetzt, aber ohne `Secure` (weil HTTP). In
Kombination mit Limitierung 12: Nur ueber Erebos sicher.

**Loesung (offen)**: Mit HTTPS (Limitierung 12) das Flag setzen.

### 14. Admin-Token in URL sichtbar (gemildert: Admin-Cookie)

Das Admin-Token wird als `?admin=<token>` in der URL uebergeben.
Das landet in Logs, Browser-History, Referrer-Headern.

**Loesung (offen)**: Admin-Token als Cookie (kurzlebig) oder
per POST-Formular. Erfordert mehr UI-Arbeit.

### 15. Forum hat keine Loeschfrist / keinen Datenexport

Threads, Posts, Accounts bleiben unbegrenzt in `forum.json`.
Es gibt keinen automatischen Cleanup, keine DSGVO-artige
Loeschfrist, keinen Datenexport pro User.

**Loesung (offen)**: Fuer Produktion: Cleanup-Job, Export-
Endpunkt, Loeschfrist.

### 16. `forum.json` waechst unbegrenzt

Alle Threads/Posts/Accounts/Sessions/Reports/Bans/Mod-Log-
Eintraege liegen in einer JSON-Datei. Bei vielen Posts wird
das Laden langsam, Schreiben blockiert.

**Loesung (offen)**: SQLite statt JSON (Migration), oder
regelmaessiger Cleanup alter Eintraege.

### 17. E2E-Payload-Grenze bei 8192 Bytes (geloest)

Der E2E-entschluesselte Payload im Rendezvous-Datenkanal ist
auf 8192 Bytes begrenzt (eine `read()`-Operation im Tunnel).
POST-Requests mit groesserem Body (>~8 KB inkl. Header) werden
abgeschnitten: Der HTTP-Handler wartet auf die fehlenden Bytes
und laeuft in einen Timeout.

**Auswirkung**: Forum-Posts mit mehr als ~7000 Zeichen Body
(nach URL-Encoding) schlagen fehl. Der ReDoS-Test mit 4000
Sternen ist betroffen, der Test mit 1000 Sternen nicht.

**Loesung (offen)**: `_keep_alive` muss `payload_data` in
Chunks senden (mehrere `http_writer.write()`), und der
E2E-decrypt muss groessere Payloads ermoeglichen (recv-Loop
statt einzelnes `read()`). Erfordert Aenderungen am
Tunnel- und E2E-Code.

### 18. Login-Rate-Limit-Umgehung per Cookie-Reset (geloest)

Bisher pruefte das Login-Rate-Limit nur pro Client-ID (Cookie).
Ein Angreifer konnte den Cookie loeschen und ein frisches Limit
bekommen.

**Geloest:** GLOBAL_LOGIN_MAX_FAILURES=50 pro 5 Minuten. Ein
globales Sicherheitsnetz zusaetzlich zum per-Client-Limit (5).
Nach 50 Fehlversuchen ueber alle Clients hinweg wird jeder
weitere Login-Versuch mit HTTP 429 blockiert.

### 19. Admin-Cookie nicht an Client gebunden (geloest)

Bisher funktionierte ein gestohlenes Admin-Cookie von jedem
Client.

**Geloest:** admin_sessions speichert client_id. is_admin_cookie
prueft die Bindung. Ein Cookie von Client A funktioniert nicht
bei Client B (HTTP 403 / "Nicht erlaubt").

### 20. Kein globales HTTP-Request-Limit (geloest)

Bisher gab es kein Limit fuer eingehende HTTP-Requests. Ein
Angreifer konnte den Dienst mit vielen Requests fluten.

**Geloest:** MAX_HTTP_REQUESTS_PER_WINDOW=500 pro 60s. Bei
Ueberschreitung: HTTP 429. Der Check laeuft VOR dem
Header-Lesen (verhindert Blockade durch riesige Header).

## Sicherheits-Haertung (OWASP-orientiert)

### Umgesetzt

| Bereich | Massnahme |
|---|---|
| Security Headers (A05) | X-Content-Type-Options, X-Frame-Options,
  Referrer-Policy, Permissions-Policy, CSP (script-src 'none') |
| Login-Rate-Limit (A07) | max. 5 Fehlversuche pro Client / 5 Min -> HTTP 429 |
| Session-Rotation (A07) | Login loescht alte Sessions (Session-Fixation-Schutz) |
| Ban-Durchsetzung (A01) | ban_user() invalidiert alle Sessions des Users |
| Markdown-Haertung (A03) | ASCII-only URLs, keine Steuerzeichen,
  noopener noreferrer, XSS-Links werden als Text gerendert |
| Exceptional Conditions (A10) | Stacktraces nur bei EREBOS_DEBUG=1 |
| Quote ohne Inline-JS | /forum/<id>/post/<idx>/quote statt onclick |
| Admin-Token (A01) | kurzlebiges Cookie (HttpOnly, SameSite=Strict,
  1h TTL) statt URL-Parameter |

### Bewusst akzeptiert

- **CSP `style-src 'unsafe-inline'`**: Die Templates nutzen
  Inline-Styles. Ein Umbau auf CSS-Klassen waere gross und
  risikoreich. CSS-Exfiltration ist nur moeglich, wenn
  HTML-Injection gelingt -- was durch _escape() und die
  Markdown-Haertung verhindert wird.
- **Kein HTTPS im Hidden Service** (Limitierung 12): Innerhalb
  des Erebos-Tunnels durch E2E geschuetzt. Fuer direkten
  Zugriff waere TLS noetig.
- **Session-Cookie ohne `Secure`** (Limitierung 13): Wegen
  HTTP. Mit HTTPS (12) nachruestbar.

## Lasttest-Ergebnisse

| Parallele Verbindungen | Erfolgreich | Latenz (pro Verbindung) |
|---|---|---|
| 10 | 10/10 (100%) | 84–93 ms |
| 50 | 50/50 (100%) | 248–320 ms |
| 100 (ulimit 256) | 81/100 (81%) | 428–622 ms |
| 100 (ulimit 4096) | 100/100 (100%) | 428–622 ms |

### Docker-Netzwerk (5 Container, Bridge 172.20.0.0/24)

| Parallele Verbindungen | Erfolgreich | Latenz (Gesamtdauer) |
|---|---|---|
| 10 | 10/10 (100%) | 232 ms |
| 50 | 50/50 (100%) | 515 ms |
| 100 | 100/100 (100%) | 840 ms |

**Beobachtung**: Bei 100 parallelen Verbindungen ist Docker genauso
schnell wie der lokale Betrieb (840 ms). Der Container-Overhead
(Bridge-Netzwerk, zusätzliche Hops) fällt gegenüber der Krypto-Arbeit
(Hybrid-Handshake, Onion-Layer, Rendezvous) nicht ins Gewicht.

## ML-KEM-1024 vs ML-KEM-768

Erebos Network nutzt **ML-KEM-1024** (NIST Level 5) fuer die
Mail-Verschluesselung. Das ist die **hoechste** NIST-Sicherheitsstufe,
aber auch die **teuerste**:

| Variante | NIST Level | Pubkey | Ciphertext | Shared Secret |
|----------|-----------|--------|------------|---------------|
| ML-KEM-512 | 1 | 800 B | 768 B | 32 B |
| ML-KEM-768 | 3 | 1.184 B | 1.088 B | 32 B |
| **ML-KEM-1024** | **5** | **1.568 B** | **1.568 B** | **32 B** |

**Level 5** ist fuer Daten gedacht, die **Jahrzehnte** geheim bleiben
muessen. **Level 3** ist fuer die meisten Anwendungen **ausreichend**.

**Warum Level 5?**
- Forschungsprototyp — maximale Sicherheit
- Kein Performance-Engpass bei Mail (Keygen: ~0.15 ms)

**Was Level 5 kostet:**
- ~30% groessere Pubkeys/Ciphertexts
- ~38-42% hoehere Bandbreite vs. ML-KEM-768

**Empfehlung fuer Produktion:**
- **Mail:** ML-KEM-768 (Level 3) ist ausreichend
- **Langzeit-Geheimnisse:** ML-KEM-1024 (Level 5)

**Aenderung:** `src/erebos_network/forum_db.py`, `hybrid_kem.py` —
`oqs.KeyEncapsulation("ML-KEM-1024")` -> `"ML-KEM-768"`.

---

## SQLCipher: KDF-Parameter

SQLCipher v4 nutzt standardmaessig **PBKDF2-HMAC-SHA-512 mit 256.000
Iterationen** zur Schluesselableitung. Erebos Network setzt
`EREBOS_DB_KEY` als **rohen 32-Byte-Hex-Key** (256 Bit Entropie) —
die KDF ist dann **nicht** sicherheitsrelevant, weil der Key bereits
maximale Entropie hat.

**Wichtig:** `EREBOS_DB_KEY` **muss** 64 Hex-Zeichen sein. Ein
schwaches Passwort wuerde die KDF nicht retten.

**Validierung:** `get_db()` prueft Laenge + Hex-Format.

## Onion-Anonymitaet: Voraussetzung paarweise verschiedener Hop-Keys

Die Anonymitaetsgarantie („Peer2 kann die naechste Layer nicht
entschluesseln") gilt nur, wenn die drei Hop-Pubkeys paarweise
verschieden sind. Bei einem degenerierten Onion mit identischen
Keys (z.B. `pack_onion_3hop(pub, pub, pub, ...)`) ist die
Entschluesselung der Mitte-Schicht durch Peer2 **korrekt** — weil
Peer2 dann zufaellig der Empfaenger dieser Schicht ist.

In der Praxis ist das irrelevant (X25519-Kollisionen ~2^-128),
aber Property-Tests muessen diesen Fall explizit ausschliessen.
`tests/test_onion_properties.py::test_peer2_cannot_decrypt_next_layer`
nutzt `hypothesis.assume(len({k1,k2,k3}) == 3)`.

**Hinweis:** `open_layer` verwendet ChaCha20-Poly1305, d.h. bei
falschem Key / manipuliertem Ciphertext wird `InvalidTag` geworfen
(kein stiller Muell-Return). Das ist korrekt und wurde durch den
Property-Test bestaetigt.

