"""SLH-DSA-SHA2-256s Signaturen (FIPS 205).

Konservativ, hash-basiert, NIST Level 5.
"""

import logging
from dataclasses import dataclass

try:
    import oqs
    HAS_LIBOQS = True
except ImportError:
    HAS_LIBOQS = False
    oqs = None

logger = logging.getLogger(__name__)


@dataclass
class SignatureKeyPair:
    """Ein SLH-DSA Schlüsselpaar."""

    public_key: bytes
    private_key: bytes

    @property
    def algorithm(self) -> str:
        return "SLH-DSA-SHA2-256s"


class PostQuantumSignature:
    """SLH-DSA-SHA2-256s Signaturen.

    NIST FIPS 205, Security Level 5.
    Stateless hash-based signatures.
    """

    ALGORITHM = "SLH-DSA-SHA2-256s"

    def __init__(self):
        if not HAS_LIBOQS:
            raise RuntimeError(
                "liboqs-python nicht installiert. "
                "Installiere: pip install liboqs-python"
            )
        self._sig = oqs.Signature(self.ALGORITHM)

    def generate_keypair(self) -> SignatureKeyPair:
        """Generiert ein SLH-DSA Schlüsselpaar."""
        public_key = self._sig.generate_keypair()
        private_key = self._sig.export_secret_key()

        logger.info(
            f"SLH-DSA KeyPair generiert: "
            f"PK={len(public_key)}B, SK={len(private_key)}B"
        )

        return SignatureKeyPair(
            public_key=public_key,
            private_key=private_key,
        )

    def sign(self, message: bytes, private_key: bytes) -> bytes:
        """Signiert eine Nachricht.

        Args:
            message: Zu signierende Nachricht
            private_key: Privater Schlüssel

        Returns:
            Signatur (bis zu 50 KB)
        """
        return self._sig.sign(message)

    def verify(
        self, message: bytes, signature: bytes, public_key: bytes
    ) -> bool:
        """Verifiziert eine Signatur."""
        return self._sig.verify(message, signature, public_key)

    @staticmethod
    def sizes() -> dict:
        """Gibt Größen zurück."""
        return {
            "algorithm": "SLH-DSA-SHA2-256s",
            "public_key": 64,
            "signature": 29792,
            "nist_level": 5,
        }
