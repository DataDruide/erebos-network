"""Threefish-512 symmetrische Verschlüsselung.

512-Bit Schlüssel = 256-Bit Post-Quanten nach Grover.
"""

import logging
import os
from dataclasses import dataclass

try:
    from pyskein import threefish
    HAS_PYSKEIN = True
except ImportError:
    HAS_PYSKEIN = False
    threefish = None

logger = logging.getLogger(__name__)


@dataclass
class ThreefishCipher:
    """Threefish-512 Verschlüsselung."""

    key: bytes
    tweak: bytes

    def __post_init__(self):
        if len(self.key) != 64:
            raise ValueError(
                f"Threefish-512 Key muss 64 Bytes sein, nicht {len(self.key)}"
            )
        if len(self.tweak) != 16:
            raise ValueError(
                f"Tweak muss 16 Bytes sein, nicht {len(self.tweak)}"
            )

    @classmethod
    def generate(cls) -> "ThreefishCipher":
        """Generiert einen zufälligen Schlüssel + Tweak."""
        return cls(
            key=os.urandom(64),
            tweak=os.urandom(16),
        )

    def encrypt(self, plaintext: bytes) -> bytes:
        """Verschlüsselt Daten (Blockgröße: 64 Bytes)."""
        if not HAS_PYSKEIN:
            raise RuntimeError("pyskein nicht installiert: pip install pyskein")

        if len(plaintext) % 64 != 0:
            raise ValueError(
                f"Plaintext muss Vielfaches von 64 sein, nicht {len(plaintext)}"
            )

        return threefish.encrypt(plaintext, self.key, self.tweak)

    def decrypt(self, ciphertext: bytes) -> bytes:
        """Entschlüsselt Daten."""
        if not HAS_PYSKEIN:
            raise RuntimeError("pyskein nicht installiert")

        if len(ciphertext) % 64 != 0:
            raise ValueError("Ciphertext muss Vielfaches von 64 sein")

        return threefish.decrypt(ciphertext, self.key, self.tweak)

    @staticmethod
    def sizes() -> dict:
        """Gibt Größen zurück."""
        return {
            "algorithm": "Threefish-512",
            "key": 64,
            "block": 64,
            "tweak": 16,
            "rounds": 72,
            "post_quantum_security": 256,
        }
