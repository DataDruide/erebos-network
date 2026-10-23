# Bekannte Limitierungen

Stand: Nach Punkt 4 (DHT-Persistenz fuer Peers)

## Was funktioniert

| Feature | Status |
|---|---|
| Erebos-Tunnel Ende-zu-Ende (HTTP ueber SOCKS5) | ✅ funktioniert |
| Hybrid-Krypto (ML-KEM + X25519 + Ed25519) | ✅ funktioniert |
| Rendezvous-Punkt mit mehreren parallelen Clients | ✅ funktioniert (Stream-Registry) |
| Parallele Verbindungen (10/50/100 gleichzeitig) | ✅ 100/100 HTTP 200 mit `ulimit -n 4096` |
| DHT-Persistenz in Peers (Descriptor ueberlebt Neustart) | ✅ funktioniert |
| Produktiver Hidden-Service als Modul (`HiddenServiceRuntime`) | ✅ funktioniert |

## Offene Limitierungen

### 1. Hidden-Service-Reconnect nach Peer-Neustart fehlt

Wenn ein Peer (insbesondere der Rendezvous-Punkt) neu startet, verliert
der Hidden-Service seine Rendezvous-Verbindung. Er registriert sich
**nicht** automatisch neu. Neue Clients finden den Descriptor zwar
(per DHT-Persistenz), aber der Rendezvous-Request geht ins Leere,
weil der Rendezvous-Punkt keinen `hidden`-Eintrag mehr hat.

**Auswirkung**: Nach einem Peer-Neustart muss der Hidden-Service
manuell neu gestartet werden.

**Loesung (offen)**: Der `HiddenServiceRuntime._keep_alive` sollte
bei Verbindungsabbruch automatisch einen Reconnect + Neu-Registrierung
versuchen (Exponential Backoff).

### 2. Parallele Verbindungen > 100 brauchen `ulimit -n`

Bei 100 parallelen Verbindungen braucht der Prozess ~500 Datei-
Deskriptoren. macOS-Standard ist `ulimit -n 256`, was zu ~19/100
Fehlschlaegen fuehrt.

**Empfehlung**: `ulimit -n 4096` vor dem Start (in derselben Shell
wie `start_all.sh`).

### 3. `conn_id` waechst monoton

Der Proxy vergibt `stream_id = conn_id & 0xFFFF`. Nach 65535
Verbindungen laufen die IDs ueber und kollidieren potenziell.

**Auswirkung**: Bei sehr langer Laufzeit mit vielen Verbindungen
koennten Stream-IDs kollidieren.

**Loesung (offen)**: `conn_id` nach Erreichen von 65535 zuruecksetzen,
oder auf 4-Byte-Stream-IDs umstellen.

### 4. Rendezvous-Punkt ist Trusted Relay (geloest: E2E-Verschluesselung)

**Geloest**: Client und Hidden-Service handeln einen gemeinsamen
E2E-Schluessel aus (X25519 + ML-KEM-1024, HKDF mit
Domain-Separation `erebos-e2e-key-v1`). Die FRAME_DATA-Payload
wird zusaetzlich mit ChaCha20-Poly1305 verschluesselt
(`e2e_flag=0x01`). peer1 leitet die verschluesselten Blobs roh
weiter und sieht keinen HTTP-Klartext mehr.

Beweis: `peer1.log` zeigt `e2e_flag=0x1` und **keinen**
HTTP-Klartext. Siehe `docs/HIDDEN_SERVICES.md`.

### 5. Hidden-Service-Schluessel nicht persistent

Der `HiddenServiceRuntime` generiert bei jedem Start ein neues
Ed25519-Schluesselpaar. Die `.erebos`-Adresse aendert sich also
bei jedem Neustart.

**Auswirkung**: Clients, die die alte Adresse gecacht haben, finden
den Hidden-Service nach einem Neustart nicht mehr.

**Loesung (offen)**: Schluesselpaar in einer Datei persistieren
(z.B. `~/.erebos/hidden_service_key.pem`), beim Start laden.

## Lasttest-Ergebnisse

Getestet mit einem Hidden-Service, 3 Peers, 1 Proxy auf einem
MacBook Air (M-Serie).

| Parallele Verbindungen | Erfolgreich | Latenz (pro Verbindung) |
|---|---|---|
| 10 | 10/10 (100%) | 84–93 ms |
| 50 | 50/50 (100%) | 248–320 ms |
| 100 (ulimit 256) | 81/100 (81%) | 428–622 ms |
| 100 (ulimit 4096) | 100/100 (100%) | 428–622 ms |

**Beobachtung**: Ab ~50 parallelen Verbindungen ist
`ulimit -n 4096` erforderlich. Der Rendezvous-Punkt skaliert
linear mit der Last.
