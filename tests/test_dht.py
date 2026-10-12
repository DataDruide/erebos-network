"""Tests für DHT."""

import pytest

from erebos_network.dht import (
    KBucket,
    PeerInfo,
    RoutingTable,
    common_prefix_length,
    generate_peer_id,
    xor_distance,
)


def test_generate_peer_id():
    """Peer-ID wird generiert."""
    id1 = generate_peer_id("127.0.0.1:8000")
    id2 = generate_peer_id("127.0.0.1:8001")
    assert len(id1) == 64
    assert id1 != id2


def test_xor_distance():
    """XOR-Distanz funktioniert."""
    id1 = "0" * 64
    id2 = "0" * 64
    assert xor_distance(id1, id2) == 0

    id3 = "0" * 63 + "1"
    assert xor_distance(id1, id3) == 1

    id4 = "0" * 62 + "ff"
    assert xor_distance(id1, id4) == 255


def test_common_prefix_length():
    """Gemeinsame Präfix-Länge funktioniert."""
    id1 = "0" * 64
    id2 = "0" * 64
    assert common_prefix_length(id1, id2) == 256

    id3 = "0" * 63 + "1"
    assert common_prefix_length(id1, id3) == 255


def test_kbucket_add():
    """KBucket fügt Peers hinzu."""
    bucket = KBucket()
    peer = PeerInfo(peer_id="a" * 64, address="127.0.0.1:8000")
    assert bucket.add(peer) is True
    assert bucket.size == 1


def test_kbucket_duplicate():
    """KBucket erkennt Duplikate."""
    bucket = KBucket()
    peer = PeerInfo(peer_id="a" * 64, address="127.0.0.1:8000")
    bucket.add(peer)
    bucket.add(peer)
    assert bucket.size == 1


def test_kbucket_remove():
    """KBucket entfernt Peers."""
    bucket = KBucket()
    peer = PeerInfo(peer_id="a" * 64, address="127.0.0.1:8000")
    bucket.add(peer)
    assert bucket.remove("a" * 64) is True
    assert bucket.size == 0


def test_routing_table_add():
    """Routing-Tabelle fügt Peers hinzu."""
    own_id = "0" * 64
    table = RoutingTable(own_id)
    peer = PeerInfo(peer_id="f" * 64, address="127.0.0.1:8000")
    assert table.add_peer(peer) is True
    assert table.total_peers == 1


def test_routing_table_no_self():
    """Routing-Tabelle fügt sich selbst nicht hinzu."""
    own_id = "a" * 64
    table = RoutingTable(own_id)
    peer = PeerInfo(peer_id=own_id, address="127.0.0.1:8000")
    assert table.add_peer(peer) is False


def test_routing_table_find_closest():
    """Routing-Tabelle findet nächste Peers."""
    own_id = "0" * 64
    table = RoutingTable(own_id)
    for i in range(10):
        peer_id = f"{i:064x}"
        peer = PeerInfo(peer_id=peer_id, address=f"127.0.0.1:{8000+i}")
        table.add_peer(peer)

    closest = table.find_closest("0" * 64, count=3)
    assert len(closest) <= 3
