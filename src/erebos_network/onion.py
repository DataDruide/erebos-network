"""Onion-Layer für Erebos Network.

Kleine, kurzlebige Verschlüsselungsschichten zum Verpacken von
Ziel-Informationen (Hop-by-Hop). Nutzt X25519 ephemer + HKDF +
ChaCha20-Poly1305.

Wire-Format einer Layer:
  ephemeral_x25519_pub (32) || nonce (12) || ciphertext+tag
"""

import os

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

EPHEMERAL_PUB_LEN = 32
NONCE_LEN = 12
HKDF_INFO = b"erebos-onion-v1"


def _derive_layer_key(shared: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=HKDF_INFO,
    ).derive(shared)


def seal_for(recipient_x25519_pub: bytes, plaintext: bytes) -> bytes:
    """Verschlüsselt plaintext für recipient_x25519_pub."""
    if len(recipient_x25519_pub) != 32:
        raise ValueError(
            f"recipient_x25519_pub muss 32 Byte sein, ist {len(recipient_x25519_pub)}"
        )

    eph_priv = X25519PrivateKey.generate()
    eph_pub = eph_priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    recipient = X25519PublicKey.from_public_bytes(recipient_x25519_pub)
    shared = eph_priv.exchange(recipient)
    key = _derive_layer_key(shared)

    nonce = os.urandom(NONCE_LEN)
    ct = ChaCha20Poly1305(key).encrypt(nonce, plaintext, None)

    return eph_pub + nonce + ct


def open_layer(recipient_x25519_priv: bytes, layer: bytes) -> bytes:
    """Öffnet eine Layer, adressiert an recipient_x25519_priv."""
    if len(layer) < EPHEMERAL_PUB_LEN + NONCE_LEN + 16:
        raise ValueError(f"Layer zu kurz: {len(layer)} Byte")

    eph_pub = layer[:EPHEMERAL_PUB_LEN]
    nonce = layer[EPHEMERAL_PUB_LEN:EPHEMERAL_PUB_LEN + NONCE_LEN]
    ct = layer[EPHEMERAL_PUB_LEN + NONCE_LEN:]

    priv = X25519PrivateKey.from_private_bytes(recipient_x25519_priv)
    shared = priv.exchange(X25519PublicKey.from_public_bytes(eph_pub))
    key = _derive_layer_key(shared)

    return ChaCha20Poly1305(key).decrypt(nonce, ct, None)
