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
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .pq_kem import PostQuantumKEM, KEMKeyPair

logger = logging.getLogger(__name__)


def derive_hybrid_key(
    x25519_shared: bytes,
    mlkem_shared: bytes,
    info: bytes = b"erebos-hybrid-kem-v1",
) -> bytes:
    """HKDF-SHA256 über (x25519_shared || mlkem_shared).

    RFC 5869, mit Domain-Separation via `info`.
    Empfohlene KDF für alle Hybrid-Schlüsselableitungen.

    Args:
        x25519_shared: X25519 Shared Secret (32 Byte)
        mlkem_shared: ML-KEM-1024 Shared Secret (32 Byte)
        info: Domain-Separation-String

    Returns:
        32-Byte Shared Secret
    """
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=info,
    ).derive(x25519_shared + mlkem_shared)


def derive_hybrid_key_legacy(
    x25519_shared: bytes,
    mlkem_shared: bytes,
) -> bytes:
    """Legacy SHA-256(concat + marker) — NUR für Rückwärtskompat.

    Wird von auth_handshake.py (Phase-1-Migration) und alten
    HybridKEM-Instanzen benutzt. Neue Anwendungen sollen
    `derive_hybrid_key` (HKDF) verwenden.
    """
    return hashlib.sha256(
        x25519_shared + mlkem_shared + b"erebos-hybrid-kem"
    ).digest()


@dataclass
class HybridKeyPair:
    """Ein Hybrid-Schluesselpaar (X25519 + ML-KEM-1024)."""

    x25519_private: bytes
    x25519_public: bytes
    mlkem_public: bytes
    mlkem_private: bytes

    def __post_init__(self):
        # Public Keys: immer validieren (auch fuer reine Empfaenger-Kontexte).
        if len(self.x25519_public) != 32:
            raise ValueError(
                f"x25519_public muss 32 Byte sein, ist {len(self.x25519_public)}"
            )
        if len(self.mlkem_public) != 1568:
            raise ValueError(
                f"mlkem_public muss 1568 Byte sein, ist {len(self.mlkem_public)}"
            )
        # Private Keys: nur wenn vorhanden (leer = Public-Only-Kontext).
        if self.x25519_private and len(self.x25519_private) != 32:
            raise ValueError(
                f"x25519_private muss 32 Byte sein, ist {len(self.x25519_private)}"
            )
        if self.mlkem_private and len(self.mlkem_private) != 3168:
            raise ValueError(
                f"mlkem_private muss 3168 Byte sein, ist {len(self.mlkem_private)}"
            )

    @property
    def algorithm(self) -> str:
        return "X25519+ML-KEM-1024"


@dataclass
class HybridCiphertext:
    """Ein Hybrid-Ciphertext."""

    x25519_ephemeral_public: bytes
    mlkem_ciphertext: bytes

    def __post_init__(self):
        if len(self.x25519_ephemeral_public) != 32:
            raise ValueError(
                f"x25519_ephemeral_public muss 32 Byte sein, "
                f"ist {len(self.x25519_ephemeral_public)}"
            )
        if len(self.mlkem_ciphertext) != 1568:
            raise ValueError(
                f"mlkem_ciphertext muss 1568 Byte sein, "
                f"ist {len(self.mlkem_ciphertext)}"
            )

    @property
    def total_size(self) -> int:
        return len(self.x25519_ephemeral_public) + len(self.mlkem_ciphertext)


class HybridKEM:
    """Hybrid Key Encapsulation Mechanism.

    Kombiniert X25519 (klassisch) mit ML-KEM-1024 (post-quantum).
    Shared Secret = SHA-256(X25519_secret || ML-KEM_secret).
    """

    def __init__(self, kdf: str = "hkdf"):
        """Hybrid KEM.

        Args:
            kdf: "hkdf"   (HKDF-SHA256, RFC 5869, Default)
                 "legacy" (SHA-256(concat), nur fuer Rueckwaerts-Kompat)
        """
        if kdf not in ("legacy", "hkdf"):
            raise ValueError(f"Unbekannte kdf: {kdf!r}")
        self.kdf = kdf
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
            public_key: Empfaenger Public Key (HybridKeyPair)

        Returns:
            (HybridCiphertext, shared_secret)

        Raises:
            TypeError: wenn public_key kein HybridKeyPair ist
        """
        if not isinstance(public_key, HybridKeyPair):
            raise TypeError(
                f"public_key muss HybridKeyPair sein, "
                f"ist {type(public_key).__name__}"
            )
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

        # 3. Kombiniere via gewählter KDF
        if self.kdf == "hkdf":
            shared_secret = derive_hybrid_key(x25519_secret, mlkem_secret)
        else:
            shared_secret = derive_hybrid_key_legacy(x25519_secret, mlkem_secret)

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
        """Decapsuliert einen Hybrid Shared Secret.

        Raises:
            TypeError: wenn ciphertext/private_key falscher Typ
        """
        if not isinstance(ciphertext, HybridCiphertext):
            raise TypeError(
                f"ciphertext muss HybridCiphertext sein, "
                f"ist {type(ciphertext).__name__}"
            )
        if not isinstance(private_key, HybridKeyPair):
            raise TypeError(
                f"private_key muss HybridKeyPair sein, "
                f"ist {type(private_key).__name__}"
            )
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

        # 3. Kombiniere via gewählter KDF
        if self.kdf == "hkdf":
            shared_secret = derive_hybrid_key(x25519_secret, mlkem_secret)
        else:
            shared_secret = derive_hybrid_key_legacy(x25519_secret, mlkem_secret)

        return shared_secret

    @staticmethod
    def sizes() -> dict:
        """Gibt Groessen zurueck."""
        return {
            "algorithm": "X25519+ML-KEM-1024",
            "kdf_default": "hkdf (RFC 5869)",
            "kdf_legacy": "sha256-concat (backward-compat only)",
            "x25519_public": 32,
            "x25519_private": 32,
            "mlkem_public": 1568,
            "mlkem_private": 3168,
            "ciphertext": 32 + 1568,
            "shared_secret": 32,
            "nist_level": 5,
            "security": "hybrid (classical + PQ)",
        }


def encrypt_mail(
    recipient_x25519_pub: bytes,
    recipient_mlkem_pub: bytes,
    plaintext: bytes,
) -> dict:
    """Verschluesselt eine Mail hybrid (X25519 + ML-KEM-1024 + ChaCha20-Poly1305).

    Returns:
        dict mit x25519_pub (hex), mlkem_ct (hex), nonce (hex), ciphertext (hex).
    """
    import os as _os
    import oqs
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey, X25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    # 1) X25519: ephemeres Paar, Shared Secret
    eph = X25519PrivateKey.generate()
    eph_pub = eph.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    shared_x = eph.exchange(X25519PublicKey.from_public_bytes(recipient_x25519_pub))

    # 2) ML-KEM-1024: encapsulate
    mlkem = oqs.KeyEncapsulation("ML-KEM-1024")
    mlkem_ct, shared_mlkem = mlkem.encap_secret(recipient_mlkem_pub)

    # 3) Hybrid-Schluessel (HKDF)
    key = derive_hybrid_key(shared_x, shared_mlkem, info=b"erebos-mail-v1")

    # 4) ChaCha20-Poly1305
    nonce = _os.urandom(12)
    ct = ChaCha20Poly1305(key).encrypt(nonce, plaintext, None)

    return {
        "x25519_pub": eph_pub.hex(),
        "mlkem_ct": mlkem_ct.hex(),
        "nonce": nonce.hex(),
        "ciphertext": ct.hex(),
    }


def decrypt_mail(
    recipient_x25519_priv: bytes,
    recipient_mlkem_priv: bytes,
    encrypted: dict,
) -> bytes:
    """Entschluesselt eine hybrid verschluesselte Mail."""
    import oqs
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey, X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    eph_pub = bytes.fromhex(encrypted["x25519_pub"])
    mlkem_ct = bytes.fromhex(encrypted["mlkem_ct"])
    nonce = bytes.fromhex(encrypted["nonce"])
    ct = bytes.fromhex(encrypted["ciphertext"])

    # 1) X25519: Shared Secret
    priv = X25519PrivateKey.from_private_bytes(recipient_x25519_priv)
    shared_x = priv.exchange(X25519PublicKey.from_public_bytes(eph_pub))

    # 2) ML-KEM-1024: decapsulate
    mlkem = oqs.KeyEncapsulation("ML-KEM-1024", recipient_mlkem_priv)
    shared_mlkem = mlkem.decap_secret(mlkem_ct)

    # 3) Hybrid-Schluessel
    key = derive_hybrid_key(shared_x, shared_mlkem, info=b"erebos-mail-v1")

    # 4) Entschluesseln
    return ChaCha20Poly1305(key).decrypt(nonce, ct, None)
