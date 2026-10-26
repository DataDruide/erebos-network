# Erebos Bedrohungsmodell

Version: 2.0
Status: Forschungsprototyp

Dieses Dokument beschreibt, was Erebos schuetzt und was nicht.
Es ist bewusst ehrlich -- Erebos ist ein Forschungsprototyp, kein
Produktions-Anonymitaetsnetzwerk.

## Was Erebos schuetzt

### 1. Inhalt (Ende-zu-Ende-Verschluesselung)

- Schutz gegen: Jeden Peer im Pfad, den Rendezvous-Punkt, den
  Proxy, den Hidden-Service-Container.
- Mechanismus: X25519 + ML-KEM-1024 (Hybrid-KEM) +
  ChaCha20-Poly1305. Schluessel nur zwischen Client und Hidden
  Service (E2E_KEY_INIT / E2E_KEY_RESP).
- Grenze: Inhalt geschuetzt, Metadaten nicht.

### 2. Lokale Angreifer (einzelne Peers)

- Schutz gegen: Einen Angreifer, der EINEN Peer kontrolliert.
- Mechanismus: 3-Hop-Onion-Routing. Jeder Hop sieht nur
  Vorgaenger und Nachfolger.
- Grenze: Ein Angreifer, der ZWEI Peers kontrolliert, kann den
  Pfad rekonstruieren.

### 3. DHT-Integritaet

- Schutz gegen: Gefaelschte Descriptors.
- Mechanismus: Ed25519-Signaturpruefung in
  DistributedDescriptorStore._verify_descriptor_value.
- Grenze: Ein Angreifer mit gueltigem Private Key (Key-Kompromitt)
  wird nicht erkannt.

### 4. Web-Schicht (Forum)

- Schutz gegen: XSS, CSRF (SameSite), Clickjacking
  (X-Frame-Options), MIME-Sniffing, Brute-Force (Login-Rate-Limit),
  Session-Fixation (Rotation), Memory-DoS (Content-Length-Limit),
  ReDoS (lineare Markdown-Verarbeitung).
- Grenze: Kein HTTPS (nur ueber Erebos-Proxy sicher),
  Admin-Token im Login-Aufruf sichtbar.

## Was Erebos NICHT schuetzt

### 1. Globale Traffic-Analyse

- Angreifer: Globaler passiver Beobachter, der Entry- und
  Exit-Traffic korreliert.
- Warum nicht: Kein Mixing (wie Nym), keine adaptiven
  Padding-Maschinen (wie Tor). 1024-Byte-Padding und 5s-Cover-
  Traffic erschweren Timing-Korrelation, verhindern sie nicht.
- Vergleich: Tor ist ebenfalls verwundbar. Nym behauptet Schutz,
  aber IACR-2026 zeigt Shape-Angriff-Verwundbarkeit.

### 2. Sybil-Angriffe

- Angreifer: Kontrolliert viele Peers.
- Warum nicht: Kein oekonomischer Sybil-Schutz (kein Staking).
  Peer-Liste statisch. Peer-Diversitaet (EREBOS_STRICT_DIVERSITY=1)
  verhindert nur, dass alle Hops aus EINEM Subnetz kommen.
- Vergleich: Tor hat keinen Sybil-Schutz. Nym hat oekonomischen
  Schutz, aber Framing-Angriffe bleiben moeglich.

### 3. Rendezvous-Punkt-Kompromittierung

- Angreifer: Kontrolliert den Rendezvous-Punkt (peer1).
- Warum nicht: Der Rendezvous-Punkt sieht, welche .erebos-Adresse
  mit welchem Client kommuniziert (Metadaten). Inhalt bleibt
  geschuetzt (E2E).
- Vergleich: Tor hat das gleiche Problem.

### 4. Harvest-Now-Decrypt-Later

- Angreifer: Zeichnet heute auf, entschluesselt in 10-20 Jahren.
- Warum nicht: Erebos nutzt Hybrid-KEM (X25519 + ML-KEM-1024).
  Post-quanten-sicher, solange ML-KEM-1024 haelt. Vorteil
  gegenueber Tor (klassische Krypto).

## Was Erebos besonders macht

1. Post-Quanten-Krypto von Anfang an (Tor: klassisch, Nym: geplant).
2. Kleine, verstaendliche Codebasis (debugbar in einer Session).
3. Web-Community als Teil des Stacks (Forum, Accounts, Moderation).

## Was Erebos NICHT ist

- Kein Tor-Ersatz (kein Schutz gegen globale Traffic-Analyse).
- Kein Nym-Ersatz (kein Mixing, kein Staking-Sybil-Schutz).
- Kein Produktionsnetzwerk (17 Limitierungen, 13 geloest).

## Empfehlung fuer Nutzer

- Nur ueber den Erebos-Proxy nutzen (nicht direkt).
- Nicht fuer sicherheitskritische Anwendungen.
- Sicherheitsluecken an den Maintainer melden (SECURITY.md).

## Referenzen

- Tor: https://support.torproject.org/about/attacks-on-onion-routing/
- Nym: https://nymtech.net/
- Erebos: docs/known-limitations.md
