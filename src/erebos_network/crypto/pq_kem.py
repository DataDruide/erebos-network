"""ML-KEM-1024 Schlüsselaustausch (FIPS 203).

NIST Level 5 - höchste Sicherheitsstufe.
32-Byte Shared Secret für symmetrische Verschlüsselung.
"""

import logging
from dataclasses import dataclass
from typing import Optional

try:
    import oqs
    HAS_LIBOQS = True
except ImportError:
    HAS_LIBOQS = False
    oqs = None

logger = logging.getLogger(__name__)


@dataclass
class KEMKeyPair:
    """Ein ML-KEM-1024 Schlüsselpaar."""

    public_key: bytes
    private_key: bytes

    @property
    def algorithm(self) -> str:
        return "ML-KEM-1024"


class PostQuantumKEM:
    """ML-KEM-1024 Key Encapsulation Mechanism.

    NIST FIPS 203, Security Level 5.
    """

    ALGORITHM = "ML-KEM-1024"
    PUBLIC_KEY_LEN = 1568
    PRIVATE_KEY_LEN = 3168
    CIPHERTEXT_LEN = 1568
    SHARED_SECRET_LEN = 32

    def __init__(self):
        if not HAS_LIBOQS:
            raise RuntimeError(
                "liboqs-python nicht installiert. "
                "Installiere: pip install liboqs-python"
            )
        self._kem = oqs.KeyEncapsulation(self.ALGORITHM)

    def generate_keypair(self) -> KEMKeyPair:
        """Generiert ein ML-KEM-1024 Schlüsselpaar.

        Returns:
            KEMKeyPair mit Public Key (1568 Bytes) und Private Key (3168 Bytes)
        """
        public_key = self._kem.generate_keypair()
        private_key = self._kem.export_secret_key()

        logger.info(
            f"ML-KEM-1024 KeyPair generiert: "
            f"PK={len(public_key)}B, SK={len(private_key)}B"
        )

        return KEMKeyPair(
            public_key=public_key,
            private_key=private_key,
        )

    def encapsulate(self, public_key: bytes) -> tuple[bytes, bytes]:
        """Encapsuliert einen Shared Secret.

        Args:
            public_key: Empfänger Public Key

        Returns:
            (ciphertext, shared_secret) - beide 1568 Bytes / 32 Bytes
        """
        ciphertext, shared_secret = self._kem.encap_secret(public_key)
        return ciphertext, shared_secret

    def decapsulate(
        self, ciphertext: bytes, private_key: bytes
    ) -> bytes:
        """Decapsuliert einen Shared Secret.

        liboqs-python 0.16.0 API: Der Private Key muss im Konstruktor
        uebergeben werden (nicht nachtraeglich via Attribut).

        Args:
            ciphertext: Ciphertext (1568 Byte fuer ML-KEM-1024)
            private_key: Empfänger Private Key (3168 Byte)

        Returns:
            32-Byte Shared Secret

        Raises:
            ValueError: bei falscher Key-Groesse
        """
        if len(private_key) != self.PRIVATE_KEY_LEN:
            raise ValueError(
                f"private_key muss {self.PRIVATE_KEY_LEN} Byte sein, "
                f"ist {len(private_key)}"
            )
        with oqs.KeyEncapsulation(self.ALGORITHM, private_key) as kem:
            return kem.decap_secret(ciphertext)

    @staticmethod
    def sizes() -> dict:
        """Gibt Schlüsselgrößen zurück."""
        return {
            "algorithm": "ML-KEM-1024",
            "public_key": 1568,
            "private_key": 3168,
            "ciphertext": 1568,
            "shared_secret": 32,
            "nist_level": 5,
        }
