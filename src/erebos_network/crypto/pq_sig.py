"""SLH-DSA Signaturen (FIPS 205).

Konservativ, hash-basiert, NIST Level 5.
Nutzt liboqs mit SLH_DSA_PURE_SHA2_256S.

Wichtig: liboqs's oqs.Signature braucht den Private Key
beim Konstruktor, um sign() aufzurufen.
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
class SignatureKeyPair:
    """Ein SLH-DSA Schluesselpaar."""

    public_key: bytes
    private_key: bytes

    @property
    def algorithm(self) -> str:
        return "SLH-DSA-SHA2-256s"


class PostQuantumSignature:
    """SLH-DSA-SHA2-256s Signaturen.

    NIST FIPS 205, Security Level 5.
    liboqs-Name: SLH_DSA_PURE_SHA2_256S

    Wichtig: liboqs ist zustandsbehaftet pro Signatur-Operation.
    Wir erstellen fuer jede Operation einen neuen Wrapper.
    """

    ALGORITHM = "SLH_DSA_PURE_SHA2_256S"
    DISPLAY_NAME = "SLH-DSA-SHA2-256s"

    def __init__(self):
        if not HAS_LIBOQS:
            raise RuntimeError(
                "liboqs-python nicht installiert. "
                "Installiere: pip install liboqs-python"
            )

    def generate_keypair(self) -> SignatureKeyPair:
        """Generiert ein SLH-DSA Schluesselpaar."""
        sig = oqs.Signature(self.ALGORITHM)
        public_key = sig.generate_keypair()
        private_key = sig.export_secret_key()

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
            private_key: Privater Schluessel

        Returns:
            Signatur
        """
        sig = oqs.Signature(self.ALGORITHM, private_key)
        return sig.sign(message)

    def verify(
        self, message: bytes, signature: bytes, public_key: bytes
    ) -> bool:
        """Verifiziert eine Signatur."""
        sig = oqs.Signature(self.ALGORITHM)
        return sig.verify(message, signature, public_key)

    @staticmethod
    def sizes() -> dict:
        """Gibt Groessen zurueck."""
        return {
            "algorithm": "SLH-DSA-SHA2-256s",
            "liboqs_name": "SLH_DSA_PURE_SHA2_256S",
            "public_key": 64,
            "signature": 29792,
            "nist_level": 5,
        }
