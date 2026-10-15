"""Post-Quantum Kryptographie fuer Erebos Network.

Basiert auf NIST-Standards:
- ML-KEM-1024 (FIPS 203) fuer Schluesselaustausch
- SLH-DSA-256s (FIPS 205) fuer Signaturen
- Threefish-512 fuer symmetrische Verschluesselung
- Hybrid (X25519 + ML-KEM-1024) fuer maximale Sicherheit

Empfohlene Symbole:
- PostQuantumKEM       ML-KEM-1024 KEM
- PostQuantumSignature SLH-DSA-256s Signaturen
- ThreefishAEAD        Threefish-512 CTR + HMAC-SHA256 (fuer Nachrichten)
- derive_hybrid_key    HKDF-SHA256-basierte Hybrid-KDF (RFC 5869)
- HybridKEM            X25519 + ML-KEM-1024 Hybrid-KEM

Legacy-Symbole (Rueckwaertskompatibilitaet, nicht fuer neue Nutzung):
- ThreefishCipher           Threefish-512 ECB (low-level Primitiv)
- derive_hybrid_key_legacy  SHA-256-basierte KDF (nicht RFC 5869)

Nicht exportiert (spezialisierte Module, direkt importieren):
- crypto.erebos_packet  -> ErebosPacket, ErebosPacketFormat
- crypto.pq_sphinx      -> PQSphinx, PQHop, PQSphinxPacket
"""

from .pq_kem import PostQuantumKEM, KEMKeyPair
from .pq_sig import PostQuantumSignature, SignatureKeyPair
from .threefish import ThreefishCipher, ThreefishAEAD
from .hybrid import HybridCrypto
from .hybrid_kem import (
    HybridKEM,
    HybridKeyPair,
    HybridCiphertext,
    derive_hybrid_key,
    derive_hybrid_key_legacy,
)

__all__ = [
    "PostQuantumKEM",
    "KEMKeyPair",
    "PostQuantumSignature",
    "SignatureKeyPair",
    "ThreefishCipher",
    "ThreefishAEAD",
    "HybridCrypto",
    "HybridKEM",
    "HybridKeyPair",
    "HybridCiphertext",
    "derive_hybrid_key",
    "derive_hybrid_key_legacy",
]
