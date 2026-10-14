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
from .threefish import ThreefishCipher

logger = logging.getLogger(__name__)


@dataclass
class HybridSession:
    """Eine Hybrid-Session."""

    cipher: ThreefishCipher
    kem_keypair: KEMKeyPair
    session_id: str

    @property
    def session_key_fingerprint(self) -> str:
        """Fingerprint des Session-Keys."""
        return hashlib.sha256(self.cipher.key).hexdigest()[:16]


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

        # Threefish-Key + Tweak + Session-ID per HKDF (RFC 5869)
        # Domain Separation via info-String.
        threefish_key = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=None,
            info=b"erebos-hybrid-threefish-key-v1",
        ).derive(shared_secret)

        tweak = HKDF(
            algorithm=hashes.SHA256(),
            length=16,
            salt=None,
            info=b"erebos-hybrid-threefish-tweak-v1",
        ).derive(shared_secret)

        session_id_bytes = HKDF(
            algorithm=hashes.SHA256(),
            length=16,
            salt=None,
            info=b"erebos-hybrid-session-id-v1",
        ).derive(shared_secret)
        session_id = session_id_bytes.hex()

        cipher = ThreefishCipher(key=threefish_key, tweak=tweak)

        session = HybridSession(
            cipher=cipher,
            kem_keypair=kem_keypair,
            session_id=session_id,
        )
        self._sessions[session_id] = session

        logger.info(f"Hybrid-Session erstellt: {session_id}")
        return session

    def encrypt(self, session_id: str, plaintext: bytes) -> bytes:
        """Verschlüsselt mit Threefish-512."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session nicht gefunden: {session_id}")

        # Padding auf 64-Byte-Blöcke
        padded = self._pad(plaintext)
        return session.cipher.encrypt(padded)

    def decrypt(self, session_id: str, ciphertext: bytes) -> bytes:
        """Entschlüsselt mit Threefish-512."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session nicht gefunden: {session_id}")

        padded = session.cipher.decrypt(ciphertext)
        return self._unpad(padded)

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
            "cipher": ThreefishCipher.sizes(),
            "hybrid": {
                "name": "ML-KEM-1024 + Threefish-512",
                "nist_level": 5,
                "post_quantum_security": 256,
            },
        }
