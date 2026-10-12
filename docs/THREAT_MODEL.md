# Erebos Network - Bedrohungsmodell

Version: 1.0
Status: Prototyp

## Angreifer-Modelle

### 1. Passiver Netzwerk-Beobachter

Faehigkeit: Sieht Traffic zwischen Knoten.

Abwehr:
- Threefish-512 verschluesselt alle Nachrichten
- Padding macht alle Nachrichten gleich gross
- Cover-Traffic verschleiert echte Nutzung

### 2. Aktiver Netzwerk-Angreifer

Faehigkeit: Kann Traffic modifizieren.

Abwehr:
- Ende-zu-Ende-Verschluesselung
- SLH-DSA-Signaturen
- Mixnet-Delays

### 3. Globaler Beobachter

Faehigkeit: Sieht alle Knoten gleichzeitig.

Abwehr:
- Mixnet mit Batching + Delays
- Cover-Traffic
- Timing-Korrelation schwer

### 4. Sybil-Angreifer

Faehigkeit: Betreibt viele Knoten.

Abwehr:
- Proof-of-Work
- Reputation + Decay
- Konsens mit Quorum

### 5. Quanten-Computer

Faehigkeit: Bricht klassische Krypto.

Abwehr:
- ML-KEM-1024 (NIST Level 5)
- SLH-DSA-SHA2-256s
- Threefish-512


### 7. Server-Timing-Angriff

Faehigkeit: Server korreliert Anfragen zeitlich.

Abwehr:
- Client-Hygiene: Timing-Jitter (0-2000ms)
- Request-Padding (1024B-Bloecke)
- Rate-Limiting (60/min)

### 8. DoS-Angriff (Descriptor Flood)

Faehigkeit: Flutet Netzwerk mit Descriptors.

Abwehr:
- Descriptor-Groessen-Limit (64KB)
- Pro-Peer-Limit (100)
- Total-Limit (10K)
- Memory-Limit (10MB/Peer)
- TTL-Cleanup

### 9. Mixnode-Adversaer

Faehigkeit: Bösartige Mixnodes korrelieren Traffic.

Abwehr:
- alpha-SS Pfad-Auswahl
- K-HF (K-Highest-Reputation-First)
- K/W (Reputation-gewichtet)
- Reduziert Angreifer-Impact um bis zu 80%

### 6. Zensur-Angreifer

Faehigkeit: Blockiert Netzwerk.

Abwehr:
- I2P dezentral
- Tor mit Bridges (geplant)
- Cover-Traffic als HTTP/HTTPS

## Was Erebos NICHT schuetzt

- Endpunkt-Kompromittierung
- Nutzer-Fehler (Passwoerter, Metadaten)
- Metadaten-Analyse
- 0-Day-Exploits
- Supply-Chain-Angriffe
- Physical Access

## Vergleich mit Tor/I2P

| Angriff | Tor | I2P | Erebos |
|---------|-----|-----|--------|
| Passiver Beobachter | Ja | Ja | Ja |
| Aktiver Angreifer | Ja | Ja | Ja |
| Globaler Beobachter | Teilweise | Teilweise | Ja |
| Sybil | Teilweise | Teilweise | Ja |
| Quanten-Computer | Nein | Nein | Ja |
| Zensur | Ja | Ja | Ja |
