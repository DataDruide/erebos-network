"""Hybrid-KEM: X25519 + ML-KEM-1024.

Kombiniert klassische und Post-Quanten-Kryptographie.
Sicher, selbst wenn einer der beiden Algorithmen gebrochen wird.

Basierend auf IETF-Standards (Hybrid Key Exchange).
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

from .pq_kem import PostQuantumKEM, KEMKeyPair

logger = logging.getLogger(__name__)


@dataclass
class HybridKeyPair:
    """Ein Hybrid-Schluesselpaar (X25519 + ML-KEM-1024)."""

    x25519_private: bytes
    x25519_public: bytes
    mlkem_public: bytes
    mlkem_private: bytes

    @property
    def algorithm(self) -> str:
        return "X25519+ML-KEM-1024"


@dataclass
class HybridCiphertext:
    """Ein Hybrid-Ciphertext."""

    x25519_ephemeral_public: bytes
    mlkem_ciphertext: bytes

    @property
    def total_size(self) -> int:
        return len(self.x25519_ephemeral_public) + len(self.mlkem_ciphertext)


class HybridKEM:
    """Hybrid Key Encapsulation Mechanism.

    Kombiniert X25519 (klassisch) mit ML-KEM-1024 (post-quantum).
    Shared Secret = SHA-256(X25519_secret || ML-KEM_secret).
    """

    def __init__(self):
        self.mlkem = PostQuantumKEM()

    def generate_keypair(self) -> HybridKeyPair:
        """Generiert ein Hybrid-Schluesselpaar."""
        x25519_priv = X25519PrivateKey.generate()
        x25519_priv_bytes = x25519_priv.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        x25519_pub_bytes = x25519_priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        mlkem_kp = self.mlkem.generate_keypair()

        logger.info("Hybrid KeyPair generiert (X25519 + ML-KEM-1024)")

        return HybridKeyPair(
            x25519_private=x25519_priv_bytes,
            x25519_public=x25519_pub_bytes,
            mlkem_public=mlkem_kp.public_key,
            mlkem_private=mlkem_kp.private_key,
        )

    def encapsulate(self, public_key: HybridKeyPair) -> tuple[HybridCiphertext, bytes]:
        """Encapsuliert einen Hybrid Shared Secret.

        Args:
            public_key: Empfaenger Public Key

        Returns:
            (HybridCiphertext, shared_secret)
        """
        # 1. X25519 ephemeral
        ephemeral_priv = X25519PrivateKey.generate()
        ephemeral_pub_bytes = ephemeral_priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        x25519_pub = X25519PublicKey.from_public_bytes(
            public_key.x25519_public
        )
        x25519_secret = ephemeral_priv.exchange(x25519_pub)

        # 2. ML-KEM encapsulate
        mlkem_ct, mlkem_secret = self.mlkem.encapsulate(
            public_key.mlkem_public
        )

        # 3. Kombiniere mit SHA-256
        shared_secret = hashlib.sha256(
            x25519_secret + mlkem_secret + b"erebos-hybrid-kem"
        ).digest()

        ciphertext = HybridCiphertext(
            x25519_ephemeral_public=ephemeral_pub_bytes,
            mlkem_ciphertext=mlkem_ct,
        )

        return ciphertext, shared_secret

    def decapsulate(
        self,
        ciphertext: HybridCiphertext,
        private_key: HybridKeyPair,
    ) -> bytes:
        """Decapsuliert einen Hybrid Shared Secret."""
        # 1. X25519
        ephemeral_pub = X25519PublicKey.from_public_bytes(
            ciphertext.x25519_ephemeral_public
        )
        x25519_priv = X25519PrivateKey.from_private_bytes(
            private_key.x25519_private
        )
        x25519_secret = x25519_priv.exchange(ephemeral_pub)

        # 2. ML-KEM decapsulate
        mlkem_secret = self.mlkem.decapsulate(
            ciphertext.mlkem_ciphertext,
            private_key.mlkem_private,
        )

        # 3. Kombiniere mit SHA-256
        shared_secret = hashlib.sha256(
            x25519_secret + mlkem_secret + b"erebos-hybrid-kem"
        ).digest()

        return shared_secret

    @staticmethod
    def sizes() -> dict:
        """Gibt Groessen zurueck."""
        return {
            "algorithm": "X25519+ML-KEM-1024",
            "x25519_public": 32,
            "x25519_private": 32,
            "mlkem_public": 1568,
            "mlkem_private": 3168,
            "ciphertext": 32 + 1568,
            "shared_secret": 32,
            "nist_level": 5,
            "security": "hybrid (classical + PQ)",
        }
