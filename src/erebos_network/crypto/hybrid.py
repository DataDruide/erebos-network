"""Hybrid-Kryptographie für Erebos Network.

Kombiniert ML-KEM-1024 + Threefish-512.
"""

import hashlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import logging
import os
from dataclasses import dataclass
from typing import Optional

from .pq_kem import PostQuantumKEM, KEMKeyPair
from .threefish import ThreefishAEAD

logger = logging.getLogger(__name__)


@dataclass
class HybridSession:
    """Eine Hybrid-Session."""

    aead: ThreefishAEAD
    kem_keypair: KEMKeyPair
    session_id: str

    @property
    def session_key_fingerprint(self) -> str:
        """Fingerprint des Session-Keys."""
        return hashlib.sha256(self.aead.key).hexdigest()[:16]


class HybridCrypto:
    """Hybrid-Kryptographie.

    ML-KEM-1024 für Schlüsselaustausch + Threefish-512 für Daten.
    """

    def __init__(self):
        self.kem = PostQuantumKEM()
        self._sessions: dict[str, HybridSession] = {}

    def create_session(self) -> HybridSession:
        """Erstellt eine neue Hybrid-Session."""
        # ML-KEM KeyPair
        kem_keypair = self.kem.generate_keypair()

        # Threefish aus Shared Secret ableiten
        ciphertext, shared_secret = self.kem.encapsulate(
            kem_keypair.public_key
        )

        # ThreefishAEAD: CTR + HMAC-SHA256, HKDF-basierte Key-Ableitung.
        aead = ThreefishAEAD.from_secret(
            shared_secret, info=b"erebos-hybrid-aead-v1",
        )

        # Session-ID separat (Domain Separation)
        session_id_bytes = HKDF(
            algorithm=hashes.SHA256(),
            length=16,
            salt=None,
            info=b"erebos-hybrid-session-id-v1",
        ).derive(shared_secret)
        session_id = session_id_bytes.hex()

        session = HybridSession(
            aead=aead,
            kem_keypair=kem_keypair,
            session_id=session_id,
        )
        self._sessions[session_id] = session

        logger.info(f"Hybrid-Session erstellt: {session_id}")
        return session

    def encrypt(self, session_id: str, plaintext: bytes) -> bytes:
        """Verschlüsselt mit ThreefishAEAD (CTR + HMAC).

        Kein Padding nötig — CTR arbeitet mit beliebiger Länge.
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session nicht gefunden: {session_id}")
        return session.aead.encrypt(plaintext)

    def decrypt(self, session_id: str, ciphertext: bytes) -> bytes:
        """Entschlüsselt mit ThreefishAEAD und verifiziert HMAC."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session nicht gefunden: {session_id}")
        return session.aead.decrypt(ciphertext)

    @staticmethod
    def _pad(data: bytes) -> bytes:
        """PKCS#7-ähnliches Padding auf 64 Bytes."""
        block_size = 64
        padding_length = block_size - (len(data) % block_size)
        padding = bytes([padding_length] * padding_length)
        return data + padding

    @staticmethod
    def _unpad(data: bytes) -> bytes:
        """Entfernt Padding."""
        padding_length = data[-1]
        return data[:-padding_length]

    @staticmethod
    def sizes() -> dict:
        """Gibt Größen zurück."""
        return {
            "kem": PostQuantumKEM.sizes(),
            "aead": ThreefishAEAD.sizes(),
            "hybrid": {
                "name": "ML-KEM-1024 + Threefish-512",
                "nist_level": 5,
                "post_quantum_security": 256,
            },
        }
