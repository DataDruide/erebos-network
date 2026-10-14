"""Tests fuer 3-Hop-Onion-Routing (Layer-Kette, kein Netzwerk)."""

import pytest

from pathlib import Path

from erebos_network.onion import (
    seal_for,
    open_layer,
    FRAME_OPEN_WIRE,
    FRAME_RELAY_WIRE,
    pack_relay_header,
    unpack_relay_header,
)

KEYS = Path(__file__).parent.parent / "erebos_keys"


def load_pub(name):
    return (KEYS / f"{name}_x25519.pub").read_bytes()


def load_priv(name):
    return (KEYS / f"{name}_x25519").read_bytes()


def build_3hop_chain(target: bytes):
    """Baut L1 (Peer-1), L2 (Peer-2), L3 (Peer-3) mit Padding."""
    l3 = seal_for(load_pub("peer3"), target)

    hdr2 = pack_relay_header(FRAME_OPEN_WIRE, 9997)
    l2 = seal_for(load_pub("peer2"), hdr2 + l3)

    hdr1 = pack_relay_header(FRAME_RELAY_WIRE, 9998)
    l1 = seal_for(load_pub("peer1"), hdr1 + l2)

    return l1, l2, l3


# ---- Relay-Header ----

def test_relay_header_roundtrip(generate_test_keys):
    """Pack/unpack eines Relay-Headers."""
    blob = pack_relay_header(FRAME_OPEN_WIRE, 9997)
    assert len(blob) == 3
    ft, port = unpack_relay_header(blob)
    assert ft == FRAME_OPEN_WIRE
    assert port == 9997


@pytest.mark.parametrize("port", [0, 1, 80, 9997, 9998, 9999, 65535])
def test_relay_header_all_ports(port, generate_test_keys):
    """Ports im uint16-Bereich funktionieren."""
    blob = pack_relay_header(FRAME_RELAY_WIRE, port)
    ft, decoded_port = unpack_relay_header(blob)
    assert ft == FRAME_RELAY_WIRE
    assert decoded_port == port


def test_relay_header_invalid_type(generate_test_keys):
    """Unbekannter Frame-Typ wirft Fehler."""
    with pytest.raises(ValueError):
        pack_relay_header(0x99, 9999)


@pytest.mark.parametrize("port", [-1, 65536, 100000])
def test_relay_header_invalid_port(port, generate_test_keys):
    """Port ausserhalb uint16 wirft Fehler."""
    with pytest.raises(ValueError):
        pack_relay_header(FRAME_RELAY_WIRE, port)


def test_relay_header_too_short(generate_test_keys):
    """Zu kurzer Header wirft Fehler."""
    with pytest.raises(ValueError):
        unpack_relay_header(b"\x01\x00")


# ---- Wire-Marker-Konsistenz ----

def test_wire_marker_distinct(generate_test_keys):
    """FRAME_OPEN_WIRE und FRAME_RELAY_WIRE sind unterscheidbar."""
    assert FRAME_OPEN_WIRE != FRAME_RELAY_WIRE
    assert FRAME_OPEN_WIRE == 0x02
    assert FRAME_RELAY_WIRE == 0x01


# ---- 3-Hop-Layer-Kette ----

def test_3hop_layer_chain(generate_test_keys):
    """3 verschachtelte Layer, jeder Peer oeffnet genau seine."""
    target = b"example.com:80"
    l1, l2, l3 = build_3hop_chain(target)

    # Peer-1 oeffnet l1
    d1 = open_layer(load_priv("peer1"), l1)
    ft1, port1 = unpack_relay_header(d1[:3])
    assert ft1 == FRAME_RELAY_WIRE
    assert port1 == 9998
    inner_l2 = d1[3:]
    assert inner_l2 == l2

    # Peer-2 oeffnet l2
    d2 = open_layer(load_priv("peer2"), inner_l2)
    ft2, port2 = unpack_relay_header(d2[:3])
    assert ft2 == FRAME_OPEN_WIRE
    assert port2 == 9997
    inner_l3 = d2[3:]
    assert inner_l3 == l3

    # Peer-3 oeffnet l3 -> direkt "host:port"
    d3 = open_layer(load_priv("peer3"), inner_l3)
    assert d3 == target


def test_3hop_layer_lengths_grow(generate_test_keys):
    """Layer wachsen von innen nach aussen (Verschachtelung)."""
    l1, l2, l3 = build_3hop_chain(b"example.com:80")
    assert len(l1) > len(l2) > len(l3)


# ---- Padding-Determinismus ueber die Kette ----

@pytest.mark.parametrize("target", [
    b"a.com:80",
    b"example.com:80",
    b"foo.bar.example.com:443",
    b"x" * 100 + b".com:80",
])
def test_padding_deterministic(target, generate_test_keys):
    """Layer-Laengen sind identisch fuer alle Ziele bis 252B."""
    l1, l2, l3 = build_3hop_chain(target)
    assert (len(l3), len(l2), len(l1)) == (316, 572, 828)


def test_3hop_wrong_order_fails(generate_test_keys):
    """Peer-3 kann l2 nicht oeffnen."""
    _, l2, _ = build_3hop_chain(b"example.com:80")
    with pytest.raises(Exception):
        open_layer(load_priv("peer3"), l2)


def test_3hop_wrong_peer_fails(generate_test_keys):
    """Peer-1 kann l3 nicht oeffnen."""
    _, _, l3 = build_3hop_chain(b"example.com:80")
    with pytest.raises(Exception):
        open_layer(load_priv("peer1"), l3)
