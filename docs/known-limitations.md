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

## Lasttest-Ergebnisse

| Parallele Verbindungen | Erfolgreich | Latenz (pro Verbindung) |
|---|---|---|
| 10 | 10/10 (100%) | 84–93 ms |
| 50 | 50/50 (100%) | 248–320 ms |
| 100 (ulimit 256) | 81/100 (81%) | 428–622 ms |
| 100 (ulimit 4096) | 100/100 (100%) | 428–622 ms |
