# Issue 001: Onion-Tunnel bricht mit IncompleteReadError ab

**Status:** offen
**Erstellt:** 2026-10-27
**Entdeckt bei:** E2E-Smoke-Test der Rotation-Reihe
**Betrifft:** Onion-Routing (Proxy -> Intro-Point -> Hidden-Service)
**Nicht betroffen:** Mail-Rotation, Krypto, Persistenz (720 Unit-Tests gruen)

## Symptom

Der SOCKS5-Proxy baut erfolgreich 2-Hop- und 3-Hop-Onions auf, aber
die Verbindung bricht waehrend der Rendezvous-Antwort ab:

    [2] Rendezvous-Antwort: {'status': 'ok', ...}
    [2] 3-Hop-Onion an peer2 gesendet
    [2] Standard-Pfad-Verbindung verloren: IncompleteReadError
    [2] Fallback-Verbindung verloren: IncompleteReadError
    [2] Alle Pfade fehlgeschlagen

Der SOCKS5-Client bekommt `HTTP 000`.

## Reproduktion

1. `docker-compose down && docker-compose up -d`
2. `sleep 15`
3. `curl --socks5-hostname localhost:4448 http://<hs>.erebos/`

## Was funktioniert

- HS-Registrierung: `Rendezvous-Paar vollstaendig!`
- Cover-Traffic: alle 20 s
- Onion-Aufbau: 2-Hop und 3-Hop erfolgreich
- Rendezvous-Antwort: `{'status': 'ok', ...}`

## Was fehlschlaegt

- HTTP-Anfrage durch den Onion-Tunnel
- Symmetrisch bei 2-Hop und 3-Hop
- `IncompleteReadError` beim Lesen der Antwort

## Vermutete Ursachen

1. Peer schliesst Verbindung zu frueh
2. Cover-Traffic-Timing
3. Rendezvous-Response-Serialisierung
4. Frame-Laengen-Mismatch (`Sende 258B`, `Response 89B`)

## Naechste Schritte

1. Peer-Logs pruefen: `docker-compose logs --tail=100 peer1 peer2 peer3 | grep -i "close|error"`
2. Rendezvous isoliert testen (ohne Onion-Hops)
3. Cover-Traffic deaktivieren (`--ack-cover` entfernen)
4. Onion-Framing pruefen

## Nicht betroffen

- Mail-Krypto (X25519, ML-KEM-1024, Ed25519, ML-DSA-65)
- Mail-Rotation (Ansatz B, 3-Zustands-Verifikation)
- Persistenz (sender_verified, verified_at)
- Lazy-Migration
- Backup/Restore
- Unit-Tests (720 passed, 21 skipped)

Bug ist orthogonal zur Mail-Dienst-Funktionalitaet.
