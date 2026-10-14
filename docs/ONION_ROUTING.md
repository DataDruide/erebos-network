# Erebos Network - Onion-Routing

Version: 1.0
Status: Prototyp

## Uebersicht

Erebos nutzt dreischichtiges Onion-Routing mit dynamischen
Relay-Headern und Padding auf feste Blockgroessen. Jeder Relay-Knoten
kennt nur seinen Vorgaenger und seinen Nachfolger - nicht die Kette,
nicht das Ziel, nicht den Ursprung.

    Browser
      | SOCKS5 (127.0.0.1:4447)
      v
    Proxy
      | Transport-Tunnel-1  (X25519 + ChaCha20-Poly1305)
      v
    Peer-1 (Relay,  :9999)
      | Transport-Tunnel-2  (X25519 + ChaCha20-Poly1305)
      v
    Peer-2 (Relay,  :9998)
      | Transport-Tunnel-3  (X25519 + ChaCha20-Poly1305)
      v
    Peer-3 (Exit,   :9997)
      | TCP
      v
    Ziel (z.B. example.com:80)

## Wissens-Trennung

| Knoten | Kennt | Kennt nicht |
|--------|-------|-------------|
| Proxy  | Ziel, alle Peer-Adressen | - |
| Peer-1 | Adresse von Peer-2 | Ziel, Peer-3, Anzahl Hops |
| Peer-2 | Adresse von Peer-3 | Ziel, Peer-1, Ursprungs-Client |
| Peer-3 | Ziel | Ursprungs-Client, andere Hops |

## Zwei Verschluesselungsebenen

### Transport-Ebene

Jeder TCP-Hop hat einen eigenen Hybrid-Handshake (X25519 + ML-KEM-1024)
mit Ed25519-Authentifizierung und ChaCha20-Poly1305. Ende-zu-Ende
zwischen den beiden Enden EINES Hops.

- Ephemere X25519-Keys pro Handshake (Forward Secrecy)
- ML-KEM-1024 Encapsulation (post-quantum)
- Ed25519-Signatur ueber version || x_pub || mlkem_pub/ct
- Session-Key = HKDF-SHA256(x25519_shared || mlkem_shared)
- ChaCha20-Poly1305 fuer die Nutzdaten

Handshake-Frame-Format (1665 Byte pro Richtung):

    version(1)  ||  x_pub(32)  ||  mlkem_pub/ct(1568)  ||  sig(64)

Version 0x02 = Hybrid PQ. Version 0x01 (klassisch) ist im Code noch
vorgesehen, wird aber nicht mehr benutzt.

Schutz gegen Harvest-Now-Decrypt-Later: der Session-Key ist nur
brechbar, wenn ein Angreifer SOWOHL X25519 ALS AUCH ML-KEM-1024
bricht.

### Onion-Ebene

Der Client verschluesselt die Zielinfo mit dem oeffentlichen
X25519-Key des Exit-Knotens. Jeder Relay-Knoten leitet die gesealte
Schicht unveraendert weiter. Nur der Exit kann sie oeffnen.

- X25519 ephemer pro Schicht
- HKDF-SHA256 zur Schluesselableitung
- ChaCha20-Poly1305 fuer die Nutzdaten
- Padding auf 256-Byte-Bloecke

## Wire-Format

### Onion-Schicht

    ephemeral_x25519_pub  (32 Byte)
    || nonce              (12 Byte)
    || ciphertext+tag     (4 + padded_plaintext + 16 Byte)

Der Klartext beginnt mit einem 4-Byte-Laengenpraefix (big endian) und
wird auf ein Vielfaches von 256 Byte aufgefuellt.

Schichtlaenge = 60 + N * 256 Byte, wobei N >= 1.

| Plaintext-Klasse | Schichtlaenge |
|------------------|---------------|
| 0-252 Byte       | 316 Byte      |
| 253-508 Byte     | 572 Byte      |
| 509-764 Byte     | 828 Byte      |

Damit leakt die Laenge des Zielnamens nicht: alle Ziele innerhalb
einer Klasse sind auf der Leitung identisch lang.

### Transport-Frame

    frame_type  (1 Byte)
    || payload  (variable Laenge, verschluesselt)

Frame-Typen:

| Wert | Name         | Bedeutung |
|------|--------------|-----------|
| 0x01 | FRAME_RELAY  | Payload = gesealte naechste Schicht |
| 0x02 | FRAME_OPEN   | Payload = gesealte innerste Schicht |
| 0x03 | FRAME_DATA   | Payload = Stream-Nutzdaten |

### Klartext je Frame-Typ nach open_layer

Transport FRAME_RELAY:

    [0]     next_frame_type  (FRAME_RELAY oder FRAME_OPEN)
    [1:3]   next_port        (uint16, big endian)
    [3:]    next_onion_layer (gesealt fuer den naechsten Peer)

Transport FRAME_OPEN:

    [0:]    "host:port"      (direkt, kein weiterer Marker)

## Schicht-Aufbau im Client

    L3 = seal_for(peer3_pub,  "host:port")                  # 316 Byte

    L2 = seal_for(peer2_pub,  hdr2 || L3)                   # 572 Byte
         wobei hdr2 = FRAME_OPEN_WIRE || uint16(9997)

    L1 = seal_for(peer1_pub,  hdr1 || L2)                   # 828 Byte
         wobei hdr1 = FRAME_RELAY_WIRE || uint16(9998)

    Transport: send_typed(FRAME_RELAY, L1) an 127.0.0.1:9999

## Ablauf pro Hop

### Peer-1 (Port 9999)

1. Transport-Frame empfaengt, entschluesselt -> FRAME_RELAY || L1
2. open_layer(peer1_x25519, L1) -> hdr1 || L2
3. unpack_relay_header(hdr1) -> (FRAME_RELAY, 9998)
4. Neuen Transport-Tunnel zu 127.0.0.1:9998 aufbauen
5. send_typed(FRAME_RELAY, L2) an Peer-2

### Peer-2 (Port 9998)

1. Transport-Frame empfaengt -> FRAME_RELAY || L2
2. open_layer(peer2_x25519, L2) -> hdr2 || L3
3. unpack_relay_header(hdr2) -> (FRAME_OPEN, 9997)
4. Neuen Transport-Tunnel zu 127.0.0.1:9997 aufbauen
5. send_typed(FRAME_OPEN, L3) an Peer-3

### Peer-3 (Port 9997, Exit)

1. Transport-Frame empfaengt -> FRAME_OPEN || L3
2. open_layer(peer3_x25519, L3) -> "host:port"
3. TCP zu host:port aufbauen
4. Stream in beide Richtungen weiterleiten

## Rueckweg

Der Rueckweg nutzt dieselben Transport-Tunnel in umgekehrter
Richtung. Die Onion-Schichten werden NICHT erneut angewendet: die
Zielantwort laeuft als Stream durch die bestehenden Tunnel-Cipher.

## Erweiterung auf N Hops

Fuer 4 Hops:

1. Keys erzeugen: python scripts/generate_keys.py peer4
2. In src/erebos_network/tunnel.py PORT_TO_PEER_NAME erweitern:

       PORT_TO_PEER_NAME = {
           9996: "peer4",
           9997: "peer3",
           9998: "peer2",
           9999: "peer1",
       }

3. In src/erebos_network/proxy.py __init__ ergaenzen:

       self.peer4_pub = (KEYS / "peer4_x25519.pub").read_bytes()
       self.peer3_port = 9996    # Peer-3 wird Relay statt Exit
       self.peer4_port = 9997    # neuer Exit

4. In _handle_client eine zusaetzliche Schicht bauen und die
   Header-Kette um eine Stufe erweitern.

Fuenf Hops analog. Die Peer-Implementierung in tunnel.py bleibt
unveraendert - sie ist topologie-agnostisch.

## Zentrale Konstanten

| Name             | Wert  | Modul     |
|------------------|-------|-----------|
| FRAME_RELAY      | 0x01  | tunnel.py |
| FRAME_OPEN       | 0x02  | tunnel.py |
| FRAME_DATA       | 0x03  | tunnel.py |
| FRAME_RELAY_WIRE | 0x01  | onion.py  |
| FRAME_OPEN_WIRE  | 0x02  | onion.py  |
| BLOCK_SIZE       | 256   | onion.py  |
| MAX_FRAME        | 65536 | tunnel.py |

## Tests

| Datei                          | Umfang |
|--------------------------------|--------|
| tests/test_onion_basic.py      | Schicht-Roundtrip, Padding, Edge-Cases |
| tests/test_onion_3hop.py       | Relay-Header, Schicht-Kette, Determinismus |
| tests/test_tunnel_framing.py   | Frame-Konstanten, HKDF, Key-Loading |
| tests/test_tunnel_handshake.py | X25519 + Ed25519-Handshake |

Aufruf:

    python -m pytest tests/ -k "onion or tunnel"

## Siehe auch

- docs/ARCHITECTURE.md - Schichtenmodell
- docs/THREAT_MODEL.md - Angreifer-Modelle
- docs/ROADMAP.md - Phasen
- src/erebos_network/onion.py - Schicht-Implementierung
- src/erebos_network/tunnel.py - Peer + Transport
- src/erebos_network/proxy.py - Schicht-Aufbau im Client
