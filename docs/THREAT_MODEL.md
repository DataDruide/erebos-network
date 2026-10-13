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


### 10. Exit-Gateway-Angreifer

Faehigkeit: Sieht Traffic am Exit-Gateway.

Abwehr:
- End-to-End Modus (kein Exit noetig)
- Hidden Services (beidseitig anonym)
- Mixnet schuetzt auch Exit-Traffic

### 11. Framing-Angreifer

Faehigkeit: Low-Stake-Nodes beschaedigen High-Reputation-Nodes.

Abwehr:
- VRF-Reputation (Hash-Commitments)
- Replay-Schutz
- Konfidenz-Metrik
- Min. verifizierte Ratings fuer Trust

### 12. Hidden-Service-Angreifer

Faehigkeit: Kompromittiert HSDir, deanonymisiert Service.

Abwehr:
- Rendezvous-Punkte (kein direkter Kontakt)
- Introduction-Points (3+ pro Service)
- PQ-Krypto fuer Descriptor
- TTL-basierte Rotation

### 13. Fingerprinting-Angreifer

Faehigkeit: Erkennt Anwendung an Traffic-Mustern.

Abwehr:
- Size-Noise (zufaellige Payload-Groessen)
- Protocol-Cover (HTTP/HTTPS/DNS/NTP/QUIC)
- Timing-Noise (0-100ms)
- Cover-Messages auf App-Ebene


### 14. Eclipse-Angreifer

Faehigkeit: Flutet Routing-Tabelle mit bösartigen Peers.

Abwehr:
- Subnetz-Diversity (max. 2 Peers pro /24)
- Loopback/Link-Local exempt
- Angreifer braucht 50+ VPS

### 15. Descriptor-Flood-Angreifer

Faehigkeit: Flutet HSDirs mit Fake-Descriptors.

Abwehr:
- Größen-Limit (64 KB)
- Pro-Service-Limit (10)
- Global-Limit (10.000)
- Rate-Limit (5/min)
- Proof-of-Work
- TTL-Cleanup

### 16. Chain-Reorg-Angreifer

Faehigkeit: Rollt Monero-Chain zurück (18-Block-Reorg 2025).

Abwehr:
- Chain-Height-Tracking
- Reorg-Detection
- Block-Hash-Mismatch-Check
- Payment-Invalidierung
- 20/30 Bestätigungen


### 17. ML-Correlation-Angreifer

Faehigkeit: ML-basierte Traffic-Correlation (RECTor).

Abwehr:
- Predictive Perturbation (Augur)
- TrafficPredictor (Markov/Transformer)
- RateShaper (Token-Bucket)
- F1: 0.9756 -> 0.0114

### 18. Shape-Analyse-Angreifer

Faehigkeit: Shape-basierte Flow-Correlation (Nym).

Abwehr:
- Flow-Splitting (S=4)
- Cover-Injection (I=2.0)
- Markov-Paket-Allocation (p=0.9)
- PR-AUC: 0.9998 -> 0.0699

### 19. Intersection-Angreifer

Faehigkeit: Deanonymisiert Hidden Service durch Intersection.

Abwehr:
- Intro-Point-Rotation (18-24h)
- Health-Rotation (>=3 Fehler)
- Age-Rotation (>24h)
- Intersection-Detection (gleicher Peer in N Sessions)
- Exponential Backoff

### 20. IoT-Sybil-Angreifer

Faehigkeit: Botnetz aus 100k IoT-Geraeten (Kimwolf).

Abwehr:
- Dynamic PoW (Difficulty skaliert)
- IP-Rate-Limit (5/Stunde)
- Subnetz-Rate-Limit (20/Stunde)
- Attack-Detection (>100/min)
- Reputation-Bypass


### 21. Website-Fingerprinting-Angreifer

Faehigkeit: Erkennt Website an Traffic-Mustern (FMWF).

Abwehr:
- TGTO (Template-Guided Obfuscation)
- TraceMorpher (Resampling + Scaling)
- SplashInjector (kurze Perturbationen)
- WF: 96% -> 36% (60% Reduktion)
- FRUGAL: ASR 2.68% bei 30% Overhead

### 22. Monero-Timing-Angreifer

Faehigkeit: OSPEAD MAP-Decoder (1-in-4.2).

Abwehr:
- Poisson-Embargo (2% -> 0.37%)
- OSPEAD-Decoys (1-in-4.2 -> ~1-in-16)
- Peer-Fallback (keine stille Degradierung)
- Cover-Txs (10-20%)
- FCMP++-Ready (100M+ Anonymitaet)

### 23. HS-Fingerprinting-Angreifer

Faehigkeit: BurstToCell-Attn (98.1% Accuracy).

Abwehr:
- BurstBreaker (Threshold=5, Padding=3)
- SplashHS (1-4 Bloecke, 64-128B)
- ResponsePadding (128B)
- Break-Pad: TPR 76.84% bei 29% Overhead

### 24. TCP-Header-Tagging-Angreifer

Faehigkeit: Versteckt Tags in TCP/IP-Headern.

Abwehr:
- IPIDNormalizer (Randomisierung)
- TimestampScrubber (untere Bits)
- WindowNormalizer (Standardwert)
- OptionScrubber (Optionen entfernt)
- TLSRecordPadder (TLS-Padding)

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
