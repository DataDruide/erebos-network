# Erebos — Architektur

## Überblick
Erebos ist ein 3-Hop-Onion-Netzwerk mit Post-Quantum-Kryptographie.
```mermaid
flowchart LR
    B[Browser] --> P[Lokaler Proxy]
    P --> D[Erebos-Daemon]
    D --> H1[Peer 1 Entry]
    H1 --> H2[Peer 2 Relay]
    H2 --> H3[Peer 3 Exit]
    H3 --> T[Ziel]
```

## Netzwerk-Topologie (Detail)

```mermaid
flowchart LR
    subgraph Client["Client (Browser / curl)"]
        B["Erebos.app<br/>SOCKS5 127.0.0.1:4448"]
    end

    subgraph Local["Lokaler Erebos-Stack"]
        P["SOCKS5-Proxy<br/>:4448"]
        A["API-Server<br/>:9050"]
        P1["Peer1 (Entry)<br/>:9999"]
        P2["Peer2 (Mix)<br/>:9998"]
        P3["Peer3 (Exit/Intro)<br/>:9997"]
        HS["Hidden-Service<br/>HTTP :8080"]
    end

    subgraph Onion["Hidden-Service-Adresse"]
        O["pkzhbyj6...erebos"]
    end

    B -->|SOCKS5| P
    P -->|3-Hop-Onion| P1
    P1 --> P2
    P2 --> P3
    P3 -->|Rendezvous| HS
    HS -.->|DHT-Descriptor| P3
    O -.->|aufgelöst zu| HS
```

**Ports im Überblick:**

| Port | Dienst | Zweck |
|------|--------|-------|
| 9050 | API-Server | Status, Peer-Liste, Hidden-Service-Registry |
| 4448 | SOCKS5-Proxy | Einstiegspunkt für Client-Anfragen |
| 9999 | Peer1 (Entry) | Erster Hop, baut Hybrid-Tunnel zum Client |
| 9998 | Peer2 (Mix) | Mittlerer Hop, leitet Relay-Frames weiter |
| 9997 | Peer3 (Exit/Intro) | Exit-Hop, entschlüsselt Onion-Layer, spricht HTTP |
| 8080 | Hidden-Service | HTTP-Server, liefert die `.erebos`-Seite |

## Verschlüsselungs-Schichten

```mermaid
flowchart TB
    subgraph L1["Layer 1 (Client -> Peer1)"]
        A1["Hybrid-Tunnel<br/>X25519 + ML-KEM<br/>(verschluesselt)"]
    end
    subgraph L2["Layer 2 (Peer1 -> Peer2)"]
        A2["Onion-Layer 2<br/>(nur Peer2 kann oeffnen)"]
    end
    subgraph L3["Layer 3 (Peer2 -> Peer3)"]
        A3["Onion-Layer 3<br/>(nur Peer3 kann oeffnen)"]
    end
    subgraph L4["Payload (Peer3 -> Hidden-Service)"]
        A4["HTTP GET /<br/>(Klartext am Exit)"]
    end

    Client["Client"] --> A1 --> A2 --> A3 --> A4 --> HS["Hidden-Service"]
```

**Eigenschaften:**

- **Transport:** Jeder Hop baut einen eigenen **Hybrid-Tunnel** (X25519 + ML-KEM-768)
  auf. Der Handshake ist im Log sichtbar (`version=0x02, x_pub=32B,
  mlkem_pub=1568B, sig=64B`).
- **Onion:** Jeder Hop entfernt genau eine Schicht. Kein Peer kennt sowohl
  Entry als auch Exit.
- **Exit-Klartext:** Am Exit-Peer (Peer3) ist der HTTP-Request im Klartext
  sichtbar – das ist bei Onion-Routing so gewollt. Der Schutz liegt darin, dass
  **kein einzelner Peer** die gesamte Kette sieht.

## Datenfluss eines `.erebos`-Requests

```mermaid
sequenceDiagram
    autonumber
    participant C as Client (curl/Browser)
    participant P as Proxy :4448
    participant P1 as Peer1 :9999
    participant P2 as Peer2 :9998
    participant P3 as Peer3 :9997
    participant HS as Hidden-Service :8080

    C->>P: SOCKS5 CONNECT pkzhbyj6...erebos:80 (remote DNS)
    P->>P1: Hybrid-Tunnel (X25519+ML-KEM) + Onion-Request
    P1->>P2: Relay (Layer 2)
    P2->>P3: Relay (Layer 3)
    P3->>HS: HTTP GET /
    HS-->>P3: 302 Found, Location: /onboard
    P3-->>P2: Relay
    P2-->>P1: Relay
    P1-->>P: Relay
    P-->>C: 302 Found
    C->>P: SOCKS5 CONNECT (erneut, /onboard)
    P->>P1: ...
    P1->>P2: ...
    P2->>P3: ...
    P3->>HS: HTTP GET /onboard
    HS-->>P3: 200 OK, 14906 Bytes HTML
    P3-->>P2: Relay
    P2-->>P1: Relay
    P1-->>P: Relay
    P-->>C: 200 OK
```

**Beobachtungen aus dem Smoke-Test:**

- Der erste Request auf `/` liefert **302 Found** mit `Location: /onboard`.
- Der Folge-Request auf `/onboard` liefert **200 OK** mit ~14.900 Bytes HTML.
- Der Hidden-Service setzt ein Session-Cookie (`forum_client_id=...`).
- Für `127.0.0.1` wird der PoW-Schutz **übersprungen** (Localhost-Ausnahme in
  `hidden_service_runtime.py`).

## Smoke-Test

Der Stack lässt sich mit einem reproduzierbaren Test prüfen:

```bash
cd ~/Projects/erebos-network
source .venv/bin/activate
python tests/test_encryption_smoke.py
```

Der Test prüft vier Dinge:

1. **Ports:** 9050, 4448, 9997, 9998, 9999, 8080 lauschen.
2. **HTTP E2E:** SOCKS5 → `.erebos` → 200 OK mit HTML (folgt Redirects).
3. **Localhost-PoW:** Im Hidden-Service-Log steht „Localhost-Client ...
   übersprungen".
4. **Verschlüsselung:** `tcpdump` auf Port 9999 zeigt keinen HTTP-Klartext.

## Bekannte Stolperfallen

- **`UnboundLocalError` in `proxy.py`:** Lokale `from .tunnel import
  ErebosTunnelClient`-Imports entfernen – der Modul-Import (Zeile 15) reicht.
- **`UnboundLocalError` in `tunnel.py`:** Lokalen `from .onion import
  open_layer`-Import entfernen – der Modul-Import (Zeile 34) reicht.
- **PoW-Blockade für localhost:** `hidden_service_runtime.py` nimmt
  `127.0.0.1`/`::1` von der PoW-Prüfung aus.
- **Browser-Proxy:** SOCKS5 (nicht HTTP) auf `127.0.0.1:4448`, mit
  `network.proxy.socks_remote_dns = true`.
