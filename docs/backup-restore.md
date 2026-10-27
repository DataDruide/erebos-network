# Backup & Wiederherstellung — Erebos Network

## Sicherheits-Warnung

Das Backup enthaelt **alle Privkeys** (`mail_keys` + `mail_key_history` mit
X25519-, ML-KEM-, Ed25519- und ML-DSA-Privkeys). Wer das Backup liest, kann:

- **alle Mails entschluesseln** (Empfaenger-Privkeys)
- **im Namen aller Nutzer signieren** (Sender-Privkeys)
- **die Hidden-Service-Adresse uebernehmen** (HS-Keys in `hs-keys`)

Das Backup muss wie ein Passwort behandelt werden:

- verschluesselt speichern (z. B. `age`, `gpg` oder ein verschluesseltes Volume)
- Zugriff auf einen kleinen Kreis beschraenken
- alte Backups sicher loeschen (`shred -u`)

## Was gehoert zum Backup

| Datei / Volume | Pfad (Host) | Pfad (Container) | Kritisch |
|---|---|---|---|
| `forum.db` | `./forum.db` | `/app/forum.db` | ja - alle Mails, Keys, User |
| HS-Keys | named volume `hs-keys` | `/root/.erebos` | ja - `.erebos`-Adresse |
| `wiki.json` | `./wiki.json` | `/app/wiki.json` | bedingt - Wiki-Inhalte |
| Peer-Keys | (ephemer) | - | nein - neu bei Neustart |

## Backup-Prozedur

### Option A - Skript (empfohlen)

    ./scripts/backup.sh
    # erzeugt ./backups/erebos-YYYYMMDD-HHMMSS/
    #   forum.db         (konsistent via sqlite3 .backup)
    #   hs-keys.tar.gz   (aus named volume)
    #   wiki.json

### Option B - manuell

    cd ~/Projects/erebos-network
    mkdir -p backups/erebos-$(date +%Y%m%d-%H%M%S)
    TS=$(date +%Y%m%d-%H%M%S)
    BK=backups/erebos-$TS

    # 1. forum.db - KONSISTENT via sqlite3 .backup (nicht cp!)
    docker-compose exec -T hidden-service python3 -c "
    import sqlite3
    src = sqlite3.connect('/app/forum.db')
    dst = sqlite3.connect('/tmp/forum.db.bak')
    src.backup(dst)
    dst.close(); src.close()
    print('sqlite3 .backup OK')
    "
    docker-compose cp hidden-service:/tmp/forum.db.bak "$BK/forum.db"

    # 2. HS-Keys (named volume)
    docker run --rm -v erebos-network_hs-keys:/data:ro -v "$PWD/$BK":/backup \
      alpine tar czf /backup/hs-keys.tar.gz -C /data .

    # 3. wiki.json
    cp wiki.json "$BK/wiki.json"

    echo "Backup: $BK"

## Restore-Prozedur

    ./scripts/restore.sh backups/erebos-YYYYMMDD-HHMMSS/

Oder manuell:

    BK=backups/erebos-YYYYMMDD-HHMMSS

    # 1. Container stoppen
    docker-compose stop hidden-service

    # 2. forum.db ersetzen
    cp "$BK/forum.db" ./forum.db

    # 3. HS-Keys ersetzen
    docker run --rm -v erebos-network_hs-keys:/data -v "$PWD/$BK":/backup \
      alpine sh -c "rm -rf /data/* && tar xzf /backup/hs-keys.tar.gz -C /data"

    # 4. wiki.json
    cp "$BK/wiki.json" ./wiki.json

    # 5. Container starten
    docker-compose start hidden-service

## Rotation und Backups

**Rotation (`rotate_mail_keys`) aendert `mail_keys.key_version`.** Ein Backup
**vor** der Rotation enthaelt die alten Privkeys und ist weiterhin gueltig -
aber es entspricht nicht dem aktuellen Stand.

**Backups sind Momentaufnahmen.** Fuer Point-in-Time-Recovery:

- **taeglich** sichern (Cron / systemd-timer)
- **mehrere Generationen** aufbewahren (z. B. 7 daily + 4 weekly + 12 monthly)
- **nach jeder Rotation** ein frisches Backup ziehen

## Was NICHT im Backup ist

- **Peer-Keys** (ephemer, bei Neustart neu)
- **Docker-Images** (ueber `docker-compose build` reproduzierbar)
- **`.env`-Datei** (enthaelt `EREBOS_FORUM_ADMIN_TOKEN` - separat sichern!)

## Wiederherstellung nach Datenverlust

Wenn `forum.db` verloren ist, aber `hs-keys` noch da sind:

- die `.erebos`-Adresse bleibt gleich
- Mails, Keys und User sind weg (kein Recovery ohne Backup)

Wenn `hs-keys` verloren ist, aber `forum.db` noch da ist:

- die `.erebos`-Adresse aendert sich (neuer HS-Key)
- alle Mails/Keys sind noch da, aber die alte Adresse ist tot

**Beides ist kritisch** - deshalb gehoeren beide ins Backup.

## Automatisierte Backups (Cron)

Fuer den Dauerbetrieb sollte das Backup **taeglich** laufen. Zwei Wege:

### Cron (einfach)

    # crontab -e (als der User, der die Backups ausfuehren soll)
    0 3 * * * /pfad/zu/erebos-network/scripts/cron_backup.sh

Das Skript `scripts/cron_backup.sh`:

- ruft `scripts/backup.sh` auf
- loggt nach `/var/log/erebos-backup.log` (Fallback: `backups/cron.log`)
- loescht Backups, die aelter als 30 Tage sind
  (konfigurierbar via `EREBOS_BACKUP_KEEP_DAYS`)

**Log-Rotation:** Damit `/var/log/erebos-backup.log` nicht unbegrenzt waechst:

    # /etc/logrotate.d/erebos-backup
    /var/log/erebos-backup.log {
        weekly
        rotate 12
        compress
        missingok
        notifempty
    }

### systemd-Timer (empfohlen fuer Produktion)

`/etc/systemd/system/erebos-backup.service`:

    [Unit]
    Description=Erebos Network Backup
    After=docker.service
    Requires=docker.service

    [Service]
    Type=oneshot
    WorkingDirectory=/opt/erebos-network
    ExecStart=/opt/erebos-network/scripts/cron_backup.sh
    User=erebos
    Group=docker

`/etc/systemd/system/erebos-backup.timer`:

    [Unit]
    Description=Erebos Network Backup Timer

    [Timer]
    OnCalendar=daily
    Persistent=true

    [Install]
    WantedBy=timers.target

Aktivieren:

    sudo systemctl daemon-reload
    sudo systemctl enable --now erebos-backup.timer
    systemctl list-timers erebos-backup.timer

**Vorteil systemd:** `Persistent=true` holt verpasste Laeufe nach
(z.B. wenn der Server nachts aus war). Logs gehen ins Journal:
`journalctl -u erebos-backup.service`.

## Restore-Test (regelmaessig!)

Ein Backup, das nie getestet wurde, ist kein Backup. Mindestens
**einmal pro Quartal** einen Restore in einer Test-Umgebung durchfuehren:

    # 1. Test-Backup ziehen
    ./scripts/backup.sh

    # 2. In Test-Umgebung einspielen (NICHT auf Production!)
    ./scripts/restore.sh backups/erebos-YYYYMMDD-HHMMSS/

    # 3. Health-Check
    curl --socks5-hostname localhost:4448 http://<hs>.erebos/

Wenn der Health-Check gruen ist, ist das Backup vertrauenswuerdig.
