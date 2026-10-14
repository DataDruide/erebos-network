"""Onion-Layer fuer Erebos Network.

Kleine, kurzlebige Verschluesselungsschichten zum Verpacken von
Ziel-Informationen (Hop-by-Hop). Nutzt X25519 ephemer + HKDF +
ChaCha20-Poly1305.

Zusaetzlich: Padding auf feste Blockgroesse, damit Layer-Laengen
keine Information ueber den Zielnamen leaken.

Wire-Format einer Layer:
  ephemeral_x25519_pub (32)
  || nonce (12)
  || ciphertext+tag (4 + padded_plaintext + 16)

Der Klartext hat ein 4-Byte Praefix (big endian), das die echte
Laenge des Original-Plaintexts enthaelt. Danach folgt das Padding
mit Zufallsbytes.
"""

import os
import struct

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

EPHEMERAL_PUB_LEN = 32
NONCE_LEN = 12
LENGTH_PREFIX_LEN = 4
TAG_LEN = 16
BLOCK_SIZE = 256

HKDF_INFO = b"erebos-onion-v1"


def _derive_layer_key(shared: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=HKDF_INFO,
    ).derive(shared)


def _pad_plaintext(plaintext: bytes) -> bytes:
    """Fuegt 4-Byte-Laengen-Praefix hinzu und padet auf BLOCK_SIZE."""
    original_len = len(plaintext)
    body = struct.pack("!I", original_len) + plaintext
    # Auf naechstes Vielfaches von BLOCK_SIZE auffuellen
    remainder = len(body) % BLOCK_SIZE
    if remainder == 0:
        pad_len = 0
    else:
        pad_len = BLOCK_SIZE - remainder
    padding = os.urandom(pad_len)
    return body + padding


def _unpad_plaintext(padded: bytes) -> bytes:
    """Liest 4-Byte-Laengen-Praefix und schneidet Padding weg."""
    if len(padded) < LENGTH_PREFIX_LEN:
        raise ValueError("Gepolsterter Klartext zu kurz")
    original_len = struct.unpack("!I", padded[:LENGTH_PREFIX_LEN])[0]
    if LENGTH_PREFIX_LEN + original_len > len(padded):
        raise ValueError(
            f"Laengen-Praefix inkonsistent: {original_len} > {len(padded) - LENGTH_PREFIX_LEN}"
        )
    return padded[LENGTH_PREFIX_LEN:LENGTH_PREFIX_LEN + original_len]


def seal_for(recipient_x25519_pub: bytes, plaintext: bytes) -> bytes:
    """Verschluesselt plaintext fuer recipient_x25519_pub.

    Nutzt ephemere X25519 und padet auf BLOCK_SIZE, damit die
    Layer-Laenge unabhaengig von der Klartext-Laenge ist.
    """
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

    padded = _pad_plaintext(plaintext)
    nonce = os.urandom(NONCE_LEN)
    ct = ChaCha20Poly1305(key).encrypt(nonce, padded, None)

    return eph_pub + nonce + ct


def open_layer(recipient_x25519_priv: bytes, layer: bytes) -> bytes:
    """Oeffnet eine Layer, adressiert an recipient_x25519_priv."""
    min_len = EPHEMERAL_PUB_LEN + NONCE_LEN + LENGTH_PREFIX_LEN + TAG_LEN
    if len(layer) < min_len:
        raise ValueError(f"Layer zu kurz: {len(layer)} Byte")

    eph_pub = layer[:EPHEMERAL_PUB_LEN]
    nonce = layer[EPHEMERAL_PUB_LEN:EPHEMERAL_PUB_LEN + NONCE_LEN]
    ct = layer[EPHEMERAL_PUB_LEN + NONCE_LEN:]

    priv = X25519PrivateKey.from_private_bytes(recipient_x25519_priv)
    shared = priv.exchange(X25519PublicKey.from_public_bytes(eph_pub))
    key = _derive_layer_key(shared)

    padded = ChaCha20Poly1305(key).decrypt(nonce, ct, None)
    return _unpad_plaintext(padded)


# ---------------------------------------------------------------------------
# Relay-Header fuer Multi-Hop
# ---------------------------------------------------------------------------
#
# Wire-Format innerhalb einer Relay-Layer:
#   byte[0]   = 0x01 (FRAME_RELAY) oder 0x02 (FRAME_OPEN)
#   byte[1]   = next_frame_type (0x01=RELAY, 0x02=OPEN)
#   byte[2:4] = next_port (uint16, big endian)
#   byte[4:]  = next_layer (an den naechsten Peer adressiert)

FRAME_RELAY_WIRE = 0x01
FRAME_OPEN_WIRE = 0x02


def pack_relay_header(next_frame_type: int, next_port: int) -> bytes:
    """Packt einen Relay-Header: 1 Byte Frame-Typ + 2 Byte Port."""
    if next_frame_type not in (FRAME_RELAY_WIRE, FRAME_OPEN_WIRE):
        raise ValueError(f"Unbekannter Frame-Typ: {next_frame_type:#x}")
    if not (0 <= next_port <= 0xFFFF):
        raise ValueError(f"Port ausserhalb uint16: {next_port}")
    return bytes([next_frame_type]) + struct.pack("!H", next_port)


def unpack_relay_header(blob: bytes) -> tuple:
    """Liest Relay-Header aus den ersten 3 Bytes."""
    if len(blob) < 3:
        raise ValueError(f"Relay-Header zu kurz: {len(blob)} Byte")
    next_frame_type = blob[0]
    next_port = struct.unpack("!H", blob[1:3])[0]
    return next_frame_type, next_port
