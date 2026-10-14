"""Tests fuer onion.py - Basisfunktionen."""

import pytest

from erebos_network.onion import (
    seal_for,
    open_layer,
    BLOCK_SIZE,
    EPHEMERAL_PUB_LEN,
    NONCE_LEN,
    LENGTH_PREFIX_LEN,
    TAG_LEN,
)

from pathlib import Path

KEYS = Path(__file__).parent.parent / "erebos_keys"
HEADER_LEN = EPHEMERAL_PUB_LEN + NONCE_LEN + TAG_LEN  # = 60


def load_pub(name):
    return (KEYS / f"{name}_x25519.pub").read_bytes()


def load_priv(name):
    return (KEYS / f"{name}_x25519").read_bytes()


# ---- Roundtrip ----

@pytest.mark.parametrize("n", [0, 1, 14, 100, 200, 239])
def test_roundtrip_short(n):
    """Roundtrip fuer kurze Plaintexte (0-239 Byte)."""
    pub = load_pub("peer1")
    priv = load_priv("peer1")
    msg = b"x" * n
    layer = seal_for(pub, msg)
    assert open_layer(priv, layer) == msg


@pytest.mark.parametrize("n", [240, 251, 252, 253, 300, 500, 600])
def test_roundtrip_block_boundary(n):
    """Roundtrip ueber Blockgrenzen (240-600 Byte)."""
    pub = load_pub("peer1")
    priv = load_priv("peer1")
    msg = b"y" * n
    layer = seal_for(pub, msg)
    assert open_layer(priv, layer) == msg


# ---- Padding ----

def test_padding_uniform_length_short():
    """Fuer alle Plaintexte bis 252B ist die Layer-Laenge identisch."""
    pub = load_pub("peer1")
    lengths = set()
    for n in range(0, 240):
        layer = seal_for(pub, b"z" * n)
        lengths.add(len(layer))
    assert len(lengths) == 1, f"Padding greift nicht: {lengths}"
    assert lengths.pop() == HEADER_LEN + BLOCK_SIZE  # 316


@pytest.mark.parametrize("n", [0, 100, 250, 252, 253, 400, 500, 600, 800])
def test_padding_wire_size(n):
    """Layer-Laenge ist immer header + N*BLOCK_SIZE."""
    pub = load_pub("peer1")
    layer = seal_for(pub, b"x" * n)
    body_len = len(layer) - HEADER_LEN
    assert body_len % BLOCK_SIZE == 0


# ---- Fehlerfaelle ----

def test_wrong_recipient_fails():
    """Layer fuer Peer-1 kann Peer-2 nicht oeffnen."""
    pub1 = load_pub("peer1")
    priv2 = load_priv("peer2")
    layer = seal_for(pub1, b"secret")
    with pytest.raises(Exception):
        open_layer(priv2, layer)


def test_tampered_layer_fails():
    """Manipulierte Layer schlaegt Tag-Check fehl."""
    pub = load_pub("peer1")
    priv = load_priv("peer1")
    layer = bytearray(seal_for(pub, b"original"))
    layer[HEADER_LEN + 10] ^= 0xFF
    with pytest.raises(Exception):
        open_layer(priv, bytes(layer))


@pytest.mark.parametrize("cut", [0, 10, 30, 50, 55])
def test_truncated_layer_fails(cut):
    """Zu kurze Layer schlaegt Laengen-Check fehl."""
    pub = load_pub("peer1")
    priv = load_priv("peer1")
    layer = seal_for(pub, b"x" * 100)
    with pytest.raises(Exception):
        open_layer(priv, layer[:cut])


# ---- Ephemeralitaet ----

def test_unique_layers():
    """Zwei Layer fuer denselben Plaintext sind unterschiedlich."""
    pub = load_pub("peer1")
    l1 = seal_for(pub, b"same")
    l2 = seal_for(pub, b"same")
    assert l1 != l2
