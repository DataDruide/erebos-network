# Peer Setup

So betreibst du einen Erebos-Peer auf einem Linux-Server (VPS) oder
einem zweiten Rechner im lokalen Netz.

## Voraussetzungen

- Linux (Ubuntu 22.04+, Debian 12+, oder vergleichbar)
- Python 3.10+
- Git
- Eine **oeffentliche IP** oder Port-Weiterleitung (fuer VPS automatisch)
- Firewall-Zugriff auf den Peer-Port (Standard: 9997)

## Schritt 1 - Repo klonen

```bash
git clone https://github.com/DataDruide/erebos-network.git
cd erebos-network
```

## Schritt 2 - venv + Abhaengigkeiten

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Schritt 3 - Peer starten

```bash
EREBOS_PEER_HOST=0.0.0.0 python3 -m erebos_network \
    --peer --peer-port 9997 --ack-cover -v
```

**Wichtig:** ```EREBOS_PEER_HOST=0.0.0.0``` (oder ```--peer-host 0.0.0.0```)
ist noetig, damit der Peer von aussen erreichbar ist. Ohne diese
Option bindet er nur auf ```127.0.0.1```.

## Schritt 4 - Firewall

Der Peer-Port muss von aussen erreichbar sein.

**ufw (Ubuntu):**
```bash
sudo ufw allow 9997/tcp
```

**firewalld (Fedora/CentOS):**
```bash
sudo firewall-cmd --add-port=9997/tcp --permanent
sudo firewall-cmd --reload
```

**Cloud-Provider (AWS, Hetzner, DigitalOcean):** Security-Group
oder Firewall-Regel fuer Port 9997 oeffnen.

## Schritt 5 - Pruefen, ob der Peer laeuft

**Auf dem Server:**
```bash
lsof -nP -iTCP:9997
# Erwartet: Python ... TCP *:9997 (LISTEN)
```

**Von einem anderen Rechner:**
```bash
nc -zv <server-ip> 9997
# Erwartet: Connection to <server-ip> 9997 port [tcp/*] succeeded!
```

**Im Log:**
```
# Erwartet:
[INFO] erebos_network.tunnel: Peer-Identitaet: peer3 (Port 9997)
[INFO] erebos_network.tunnel: Peer-Server laeuft auf 0.0.0.0:9997
```

## Schritt 6 - Dauerhaft laufen lassen

Fuer einen VPS: ```systemd```-Service anlegen.

```bash
sudo tee /etc/systemd/system/erebos-peer.service > /dev/null << 'EOF'
[Unit]
Description=Erebos Peer Server
After=network.target

[Service]
Type=simple
User=erebos
WorkingDirectory=/home/erebos/erebos-network
Environment="EREBOS_PEER_HOST=0.0.0.0"
ExecStart=/home/erebos/erebos-network/.venv/bin/python3 -m erebos_network --peer --peer-port 9997 --ack-cover
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now erebos-peer
sudo systemctl status erebos-peer
```

## Was ein Peer tut

Ein Peer ist ein **Knoten im Erebos-Netzwerk**. Er:

- Nimmt Tunnel-Verbindungen von anderen Peers an
- Leitet ```FRAME_RELAY```-Frames weiter (3-Hop-Onion)
- Empfaengt ```FRAME_COVER```-Frames und verwirft sie
- Sendet optional ```FRAME_COVER_ACK```-Frames (mit ```--ack-cover```)

Ein Peer **sieht nicht**, welche Ziele ein Client aufruft - er sieht nur
die verschluesselten Onion-Layer (X25519 + ML-KEM-1024).

## Sicherheit

- **Private Keys** liegen unter ```erebos_keys/```. Niemals committen.
- **Logs** koennen Metadaten enthalten (Timing, Peer-IDs). Nicht
  oeffentlich zugaenglich machen.
- **Updates:** ```git pull && pip install -e .``` und Service neu starten.

## Bekannte Einschraenkungen

- Der Peer hat **keine automatische Peer-Discovery**. Er kennt nur
  die Peers, die in ```PORT_TO_PEER_NAME``` konfiguriert sind.
- **Kein NAT-Traversal.** Der Peer braucht eine oeffentliche IP oder
  Port-Weiterleitung.
- **Reputation** wird noch nicht dezentral geteilt. Jeder Peer
  bewertet lokal.

## Fragen?

Oeffne ein Issue mit dem Label ```peer-setup```.

