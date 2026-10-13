# Erebos Network - Post-Quanten-Kryptographie

Version: 1.0
NIST-Level: 5

## Warum Post-Quanten?

Klassische Krypto (RSA, ECDH, Ed25519) ist anfaellig fuer Quanten-Computer:

- Shor's Algorithmus bricht RSA, ECDH, Ed25519
- Grover's Algorithmus halbiert effektive Schluessellaenge

Harvest-Now-Decrypt-Later: Daten, die heute abgefangen werden,
koennen in 10-20 Jahren entschluesselt werden.

Tor und I2P sind nicht quantenresistent.

## NIST-Standards (2024)

| Standard | Algorithmus | Zweck |
|----------|-------------|-------|
| FIPS 203 | ML-KEM (Kyber) | Schluesselaustausch |
| FIPS 204 | ML-DSA (Dilithium) | Signaturen |
| FIPS 205 | SLH-DSA (SPHINCS+) | Konservative Signaturen |

## Erebos' Wahl

### 1. ML-KEM-1024 (FIPS 203)

NIST Level 5 - hoechste Sicherheitsstufe.

| Parameter | Wert |
|-----------|------|
| Public Key | 1568 Bytes |
| Private Key | 3168 Bytes |
| Ciphertext | 1568 Bytes |
| Shared Secret | 32 Bytes |

### 2. SLH-DSA-SHA2-256s (FIPS 205)

Konservativ, hash-basiert.

| Parameter | Wert |
|-----------|------|
| Public Key | 64 Bytes |
| Signature | ~30 KB |
| Hash | SHA-256 |

Warum SLH-DSA (nicht ML-DSA)?
- Keine Lattice-Annahmen
- Konservativ
- Kleine Public Keys
- Stateless

### 3. Threefish-512

Symmetrische Verschluesselung mit 512-Bit-Schluessel.

| Parameter | Wert |
|-----------|------|
| Schluessel | 512 Bit (64 Bytes) |
| Block | 512 Bit (64 Bytes) |
| Runden | 72 |
| Tweak | 128 Bit (16 Bytes) |

Warum Threefish (nicht AES-256)?
- 512-Bit Schluessel = 256-Bit PQ
- 512-Bit Block
- Software-freundlich
- Von Bruce Schneier

### 4. Hybrid-Krypto

ML-KEM-1024 + Threefish-512

Ablauf:
1. ML-KEM-1024 erzeugt Shared Secret (32 Bytes)
2. SHA-512 leitet Threefish-Key (64 Bytes) + Tweak (16 Bytes) ab
3. Threefish-512 verschluesselt Daten


## Hybrid-KEM (X25519 + ML-KEM-1024)

Zusaetzlich zu purem ML-KEM-1024 bietet Erebos einen Hybrid-Modus:

1. X25519 ephemeral Key Exchange (klassisch)
2. ML-KEM-1024 Encapsulation (post-quantum)
3. Shared Secret = SHA-256(X25519_secret || ML-KEM_secret)

Vorteil: Sicher, selbst wenn einer der beiden Algorithmen gebrochen wird.

## PQ-Sphinx (Forschungsprototyp)

Klassisches Sphinx nutzt DH-Eigenschaften. PQ-KEMs teilen diese nicht.
Erebos implementiert ein geschichtetes ML-KEM-1024-Format:

- Pro Hop: ML-KEM-1024 Encapsulation
- Layer = KEM-Ciphertext + XOR-verschluesselter Payload
- MAC ueber alle Layer

Dies ist ein Forschungsprototyp - das erste PQ-Mixnet-Format.

## Vergleich mit Tor/I2P

| Komponente | Tor | I2P | Erebos |
|------------|-----|-----|--------|
| Schluesselaustausch | ECDH | ECDH | ML-KEM-1024 |
| Signaturen | Ed25519 | Ed25519 | SLH-DSA-256s |
| Symmetrisch | AES-256 | AES-256 | Threefish-512 |
| Post-Quanten | Nein | Nein | Ja NIST 5 |

## Overhead

| Operation | Klassisch | Post-Quanten | Faktor |
|-----------|-----------|--------------|--------|
| Key-Austausch | 32 B | 1568 B | 49x |
| Signatur | 64 B | ~30 KB | 470x |
| Symmetrisch | 32 B | 64 B | 2x |

## Krypto-Integration-Tests

18 Integration-Tests pruefen, dass der GESAMTE Datenpfad
verschluesselt ist - basierend auf dem Radicle-Bug (2026).

- Jedes E2E-Paket verschluesselt
- Kein Klartext-Marker in irgendeiner Schicht
- Nicht-etablierte Sessions lehnen ab
- Threefish/Hybrid-Crypto Round-Trips

## Bibliotheken

- liboqs-python - Open Quantum Safe (ML-KEM, SLH-DSA)
- pyskein - Threefish-512

## Referenzen

1. NIST FIPS 203 (2024): ML-KEM
2. NIST FIPS 204 (2024): ML-DSA
3. NIST FIPS 205 (2024): SLH-DSA
4. IEEE QuantumOnion (2026): PQ in Onion-Routing
5. Schneier et al. (2010): Threefish
