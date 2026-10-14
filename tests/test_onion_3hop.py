"""Unit-Test fuer 3-Hop-Onion-Routing (kein Netzwerk)."""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from erebos_network.onion import (
    seal_for,
    open_layer,
    FRAME_OPEN_WIRE,
    FRAME_RELAY_WIRE,
    pack_relay_header,
    unpack_relay_header,
)
from erebos_network.tunnel import FRAME_OPEN, FRAME_RELAY

KEYS = ROOT / "erebos_keys"


def load_pub(name):
    return (KEYS / f"{name}_x25519.pub").read_bytes()


def load_priv(name):
    return (KEYS / f"{name}_x25519").read_bytes()


def test_relay_header_roundtrip():
    frame_type = FRAME_OPEN
    next_port = 9997
    blob = pack_relay_header(frame_type, next_port)
    assert len(blob) == 3, f"Header sollte 3 Byte sein, ist {len(blob)}"
    ft, port = unpack_relay_header(blob)
    assert ft == frame_type
    assert port == next_port
    print("  relay-header roundtrip OK")


def test_wire_marker_constants():
    assert isinstance(FRAME_OPEN_WIRE, int)
    assert isinstance(FRAME_RELAY_WIRE, int)
    assert FRAME_OPEN_WIRE != FRAME_RELAY_WIRE
    print(f"  FRAME_OPEN_WIRE={FRAME_OPEN_WIRE:#x} FRAME_RELAY_WIRE={FRAME_RELAY_WIRE:#x}")


def _build_3hop_chain(target: bytes):
    peer1_pub = load_pub("peer1")
    peer2_pub = load_pub("peer2")
    peer3_pub = load_pub("peer3")

    l3_plain = bytes([FRAME_OPEN]) + target
    l3 = seal_for(peer3_pub, l3_plain)

    hdr2 = pack_relay_header(FRAME_OPEN_WIRE, 9997)
    l2_plain = bytes([FRAME_RELAY]) + hdr2 + l3
    l2 = seal_for(peer2_pub, l2_plain)

    hdr1 = pack_relay_header(FRAME_RELAY_WIRE, 9998)
    l1_plain = bytes([FRAME_RELAY]) + hdr1 + l2
    l1 = seal_for(peer1_pub, l1_plain)

    return l1, l2, l3


def test_3hop_layer_chain():
    target = b"example.com:80"
    l1, l2, l3 = _build_3hop_chain(target)

    print(f"  L1 len={len(l1)}  L2 len={len(l2)}  L3 len={len(l3)}")
    assert len(l1) > len(l2) > len(l3)
    assert (len(l3) - 60) % 256 == 0
    assert (len(l2) - 60) % 256 == 0
    assert (len(l1) - 60) % 256 == 0

    peer1_priv = load_priv("peer1")
    peer2_priv = load_priv("peer2")
    peer3_priv = load_priv("peer3")

    d1 = open_layer(peer1_priv, l1)
    assert d1[0] == FRAME_RELAY
    ft1, port1 = unpack_relay_header(d1[1:4])
    assert ft1 == FRAME_RELAY_WIRE
    assert port1 == 9998
    inner_l2 = d1[4:]
    assert inner_l2 == l2
    print("  Peer-1 oeffnet L1, sieht nur Relay-Auftrag nach :9998")

    d2 = open_layer(peer2_priv, inner_l2)
    assert d2[0] == FRAME_RELAY
    ft2, port2 = unpack_relay_header(d2[1:4])
    assert ft2 == FRAME_OPEN_WIRE
    assert port2 == 9997
    inner_l3 = d2[4:]
    assert inner_l3 == l3
    print("  Peer-2 oeffnet L2, sieht nur Relay-Auftrag nach :9997 (als OPEN)")

    d3 = open_layer(peer3_priv, inner_l3)
    assert d3[0] == FRAME_OPEN
    assert d3[1:] == target
    print("  Peer-3 oeffnet L3, sieht Ziel example.com:80")

    print("  3-HOP-LAYER-CHAIN OK")


def test_padding_makes_layers_deterministic():
    targets = [
        b"a.com:80",
        b"example.com:80",
        b"foo.bar.example.com:443",
        b"x" * 100 + b".com:80",
    ]
    seen = set()
    for t in targets:
        l1, l2, l3 = _build_3hop_chain(t)
        seen.add((len(l1), len(l2), len(l3)))
        print(f"  target-len={len(t):4d}B -> L1={len(l1)} L2={len(l2)} L3={len(l3)}")

    assert len(seen) == 1, f"Layer-Laengen variieren: {seen}"
    print("  alle Ziele innerhalb 252B -> identische Layer-Laengen")
    print("  PADDING-DETERMINISMUS OK")


if __name__ == "__main__":
    print("=== test_relay_header_roundtrip ===")
    test_relay_header_roundtrip()
    print()
    print("=== test_wire_marker_constants ===")
    test_wire_marker_constants()
    print()
    print("=== test_3hop_layer_chain ===")
    test_3hop_layer_chain()
    print()
    print("=== test_padding_makes_layers_deterministic ===")
    test_padding_makes_layers_deterministic()
    print()
    print("ALLE 3-HOP-TESTS OK")
