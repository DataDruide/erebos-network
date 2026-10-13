"""Threefish-512 symmetrische Verschluesselung.

512-Bit Schluessel = 256-Bit Post-Quanten nach Grover.

Nutzt pyskein (Modul: skein) wenn importierbar.
Blockgroesse: 64 Bytes.
"""

import logging
import os
from dataclasses import dataclass

HAS_PYSKEIN = False
_threefish_factory = None

try:
    from skein import threefish as _tf_factory
    _threefish_factory = _tf_factory
    HAS_PYSKEIN = True
except (ImportError, ModuleNotFoundError, AttributeError):
    pass


logger = logging.getLogger(__name__)

if HAS_PYSKEIN:
    logger.info("Threefish: pyskein backend")
else:
    logger.warning("Threefish: pyskein NICHT verfuegbar")


@dataclass
class ThreefishCipher:
    """Threefish-512 Verschluesselung.

    API: threefish(key, tweak).encrypt_block(data)
    Blockgroesse: 64 Bytes
    """

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
        """Generiert einen zufaelligen Schluessel + Tweak."""
        return cls(
            key=os.urandom(64),
            tweak=os.urandom(16),
        )

    def _make_cipher(self):
        """Erstellt ein pyskein-Cipher-Objekt."""
        if not HAS_PYSKEIN:
            raise RuntimeError(
                "pyskein nicht verfuegbar. "
                "Installiere: pip install pyskein"
            )
        return _threefish_factory(self.key, self.tweak)

    def encrypt(self, plaintext: bytes) -> bytes:
        """Verschluesselt Daten (Vielfaches von 64 Bytes)."""
        if not HAS_PYSKEIN:
            raise RuntimeError("pyskein nicht verfuegbar")

        if len(plaintext) % 64 != 0:
            raise ValueError(
                f"Plaintext muss Vielfaches von 64 sein, nicht {len(plaintext)}"
            )

        cipher = self._make_cipher()
        result = b""
        for i in range(0, len(plaintext), 64):
            block = plaintext[i:i+64]
            result += cipher.encrypt_block(block)
        return result

    def decrypt(self, ciphertext: bytes) -> bytes:
        """Entschluesselt Daten (Vielfaches von 64 Bytes)."""
        if not HAS_PYSKEIN:
            raise RuntimeError("pyskein nicht verfuegbar")

        if len(ciphertext) % 64 != 0:
            raise ValueError("Ciphertext muss Vielfaches von 64 sein")

        cipher = self._make_cipher()
        result = b""
        for i in range(0, len(ciphertext), 64):
            block = ciphertext[i:i+64]
            result += cipher.decrypt_block(block)
        return result

    @staticmethod
    def sizes() -> dict:
        """Gibt Groessen zurueck."""
        return {
            "algorithm": "Threefish-512",
            "key": 64,
            "block": 64,
            "tweak": 16,
            "rounds": 72,
            "post_quantum_security": 256,
            "backend": "pyskein" if HAS_PYSKEIN else "unavailable",
        }
