# Erebos — Freundes-Paket

Willkommen bei Erebos! Diese Anleitung führt dich Schritt für Schritt durch die Installation und Nutzung des Erebos-Browsers mit dem Freundes-Proxy.

**Was du brauchst:**
- Einen Mac (Apple Silicon oder Intel)
- Die Datei `Erebos.dmg` (in diesem Paket)
- Die Datei `start_friend_proxy.sh` (in diesem Paket)
- Internetzugang

**Was du bekommst:**
- Den Erebos-Browser mit integriertem SOCKS5-Proxy
- Zugang zum Erebos-Netzwerk über den Hetzner-Bootstrap-Peer
- `.erebos`-Adressen (Wiki, Chat, Mail, Search, Hidden Services)
- **Erebos-Theme** (Matrix-Regen, Scanlines, Vignette, Custom Cursor)
- **Profil-Panel** (Avatar, XP, Token, Achievements)
- **Netzwerk-Karte** (echte Peers, Datenfluss)
- **Erebos-Zeit** (eigene Zeitrechnung)
- **Achievements** (Toasts für erste Besuche)
- **Sound-Design** (Klick-Sounds, Ambient)

---

## 1. Erebos-Browser installieren

1. Öffne die Datei `Erebos.dmg` (Doppelklick).
2. Ziehe das Erebos-Symbol in den **Programme**-Ordner.
3. Öffne Erebos aus dem Programme-Ordner (beim ersten Start: Rechtsklick → **Öffnen**, um die macOS-Sicherheitswarnung zu umgehen).
4. Der Browser startet mit der Erebos-Startseite.

> **Hinweis:** Beim ersten Start kann macOS fragen, ob die App aus dem Internet geladen werden darf. Klicke auf **Öffnen**.

---

## 2. Freundes-Proxy starten

Der Proxy verbindet deinen Browser mit dem Erebos-Netzwerk über den Hetzner-Bootstrap-Peer.

1. Öffne ein **Terminal** (Programme → Dienstprogramme → Terminal).
2. Wechsle in den Ordner, in dem `start_friend_proxy.sh` liegt:

        cd ~/Downloads/Erebos-Friends

3. Mache das Skript ausführbar (einmalig):

        chmod +x start_friend_proxy.sh

4. Starte den Proxy:

        ./start_friend_proxy.sh

5. Du solltest sehen:

        Starte Erebos-Proxy (verbinde mit 167.233.111.144:9996)...
        Erebos SOCKS5-Proxy laeuft auf 127.0.0.1:4448

**Wichtig:** Lass das Terminal-Fenster offen — der Proxy läuft, solange das Fenster geöffnet ist. Zum Beenden: `Strg + C`.

---

## 3. Browser konfigurieren (SOCKS5-Proxy)

Der Erebos-Browser muss wissen, dass er den Proxy auf `127.0.0.1:4448` verwenden soll.

### Option A: Systemweiter Proxy (empfohlen)

1. Öffne **Systemeinstellungen** → **Netzwerk** → **Proxies**.
2. Aktiviere **SOCKS5-Proxy**.
3. Trage ein:
   - **Server:** `127.0.0.1`
   - **Port:** `4448`
4. Klicke auf **OK**.

### Option B: Nur im Erebos-Browser

1. Öffne Erebos.
2. Gehe zu **Einstellungen** → **Netzwerk** → **Proxy**.
3. Wähle **SOCKS5** und trage `127.0.0.1:4448` ein.
4. Speichere die Einstellungen.

---

## 4. Erste Schritte — `.erebos`-Adressen aufrufen

Erebos-Seiten haben die Endung `.erebos` (z. B. `r7bsxkgo7tiaqa3vdcyzgp5qziq5g7cehv4q5pl7fnmhmwk7eudq.erebos`).

**Teste den Proxy mit dieser Adresse:**

        http://r7bsxkgo7tiaqa3vdcyzgp5qziq5g7cehv4q5pl7fnmhmwk7eudq.erebos/welcome

Wenn die Seite lädt, funktioniert alles.

**Weitere Seiten:**

        http://r7bsxkgo7tiaqa3vdcyzgp5qziq5g7cehv4q5pl7fnmhmwk7eudq.erebos/wiki
        http://r7bsxkgo7tiaqa3vdcyzgp5qziq5g7cehv4q5pl7fnmhmwk7eudq.erebos/chat
        http://r7bsxkgo7tiaqa3vdcyzgp5qziq5g7cehv4q5pl7fnmhmwk7eudq.erebos/mail
        http://r7bsxkgo7tiaqa3vdcyzgp5qziq5g7cehv4q5pl7fnmhmwk7eudq.erebos/search

---

## 5. Fehlerbehebung

### „Connection refused" oder „Proxy nicht erreichbar"
- Prüfe, ob der Proxy läuft:

        lsof -i :4448

  (sollte eine Zeile mit `python` zeigen)
- Starte den Proxy neu: `Strg + C` im Terminal, dann `./start_friend_proxy.sh`.

### „Keine HTTP-Antwort vom Hidden Service"
- Prüfe, ob der Hetzner-Peer erreichbar ist:

        ping 167.233.111.144

- Warte 10–15 Sekunden und lade die Seite neu.

### „E2E-Schluesselaustausch fehlgeschlagen"
- Das ist meist harmlos — der Proxy fällt auf Klartext zurück.
- Lade die Seite neu.

### Der Browser lädt unendlich
- Prüfe, ob der Proxy noch läuft (`lsof -i :4448`).
- Prüfe, ob die `.erebos`-Adresse korrekt ist.
- Starte den Proxy neu.

---

## 6. Sicherheit & Datenschutz

- Der Proxy verbindet sich **nur** mit dem Hetzner-Peer (`167.233.111.144:9996`).
- Der Datenverkehr ist **E2E-verschlüsselt** (X25519 + ML-KEM-1024).
- Deine IP-Adresse wird **nicht** an die `.erebos`-Seiten weitergegeben.
- Der Proxy läuft **nur lokal** (`127.0.0.1:4448`) — niemand sonst kann ihn erreichen.

---

## 7. Proxy beenden

- **Terminal:** `Strg + C` im Fenster, wo der Proxy läuft.
- **Systemweiter Proxy:** Systemeinstellungen → Netzwerk → Proxies → SOCKS5 deaktivieren.

---

**Viel Spaß mit Erebos!**
