"""Tests fuer Erebos-Paketformat."""

import pytest

from erebos_network.crypto.erebos_packet import (
    ErebosPacket,
    ErebosPacketFormat,
    HopInfo,
    PacketError,
)
from erebos_network.crypto.pq_kem import PostQuantumKEM


def make_hops(n: int) -> list[HopInfo]:
    """Erzeugt n Test-Hops."""
    kem = PostQuantumKEM()
    hops = []
    for i in range(n):
        kp = kem.generate_keypair()
        hops.append(HopInfo(
            node_id=f"node{i}",
            public_key=kp.public_key,
            routing_info=f"route{i}".encode(),
        ))
    return hops


def test_packet_init():
    """Format initialisiert."""
    f = ErebosPacketFormat()
    assert f.stats["packets_created"] == 0


def test_packet_create():
    """Paket wird erstellt."""
    f = ErebosPacketFormat()
    hops = make_hops(3)
    packet = f.create_packet(hops, b"Hello, Erebos!")
    assert packet.num_hops == 3
    assert packet.total_size > 0
    assert len(packet.mac) == 32


def test_packet_too_few_hops():
    """Zu wenige Hops werfen Fehler."""
    f = ErebosPacketFormat()
    hops = make_hops(1)
    with pytest.raises(PacketError):
        f.create_packet(hops, b"data")


def test_packet_too_many_hops():
    """Zu viele Hops werfen Fehler."""
    f = ErebosPacketFormat()
    hops = make_hops(10)
    with pytest.raises(PacketError):
        f.create_packet(hops, b"data")


def test_packet_sizes():
    """Groessen sind korrekt."""
    sizes = ErebosPacketFormat.sizes(3)
    assert sizes["num_hops"] == 3
    assert sizes["min_hops"] == 2
    assert sizes["max_hops"] == 7
    assert sizes["magic"] == "EREBOS"


def test_packet_pad_unpad():
    """Padding funktioniert."""
    data = b"Hello"
    padded = ErebosPacketFormat._pad(data)
    assert len(padded) % 64 == 0
    unpadded = ErebosPacketFormat._unpad(padded)
    assert unpadded == data


def test_packet_layers_differ():
    """Layer sind unterschiedlich."""
    f = ErebosPacketFormat()
    hops = make_hops(3)
    packet = f.create_packet(hops, b"Hello")
    assert len(set(packet.layers)) == len(packet.layers)


def test_packet_unique_per_call():
    """Jedes Paket ist einzigartig."""
    f = ErebosPacketFormat()
    hops = make_hops(3)
    p1 = f.create_packet(hops, b"Hello")
    p2 = f.create_packet(hops, b"Hello")
    assert p1.layers != p2.layers


def test_packet_stats():
    """Statistiken funktionieren."""
    f = ErebosPacketFormat()
    hops = make_hops(3)
    f.create_packet(hops, b"Hello")
    stats = f.stats
    assert stats["packets_created"] == 1
    assert stats["bytes_created"] > 0
