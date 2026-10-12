"""Tests für Peer-Discovery."""

import pytest

from erebos_network.discovery import (
    DiscoveryConfig,
    PeerDiscovery,
)


def test_discovery_basic():
    """Discovery initialisiert."""
    d = PeerDiscovery("127.0.0.1:8000")
    assert d.peer_count == 0


def test_discovery_add_peer():
    """Peer wird hinzugefügt."""
    d = PeerDiscovery("127.0.0.1:8000")
    assert d.add_peer("127.0.0.1:8001") is True
    assert d.peer_count == 1


def test_discovery_no_self():
    """Eigener Peer wird nicht hinzugefügt."""
    d = PeerDiscovery("127.0.0.1:8000")
    assert d.add_peer("127.0.0.1:8000") is False


def test_discovery_bootstrap():
    """Bootstrap fügt Peers hinzu."""
    config = DiscoveryConfig(
        bootstrap_peers=["127.0.0.1:8001", "127.0.0.1:8002"]
    )
    d = PeerDiscovery("127.0.0.1:8000", config)
    added = d.bootstrap()
    assert added == 2
    assert d.peer_count == 2


def test_discovery_lookup():
    """Lookup findet Peers."""
    d = PeerDiscovery("127.0.0.1:8000")
    d.add_peer("127.0.0.1:8001")
    results = d.lookup("0" * 64)
    assert len(results) >= 1


def test_discovery_remove():
    """Peer wird entfernt."""
    d = PeerDiscovery("127.0.0.1:8000")
    d.add_peer("127.0.0.1:8001")
    from erebos_network.dht import generate_peer_id
    peer_id = generate_peer_id("127.0.0.1:8001")
    assert d.remove_peer(peer_id) is True


def test_discovery_stats():
    """Statistiken funktionieren."""
    d = PeerDiscovery("127.0.0.1:8000")
    d.add_peer("127.0.0.1:8001")
    stats = d.get_stats()
    assert stats["peers_added"] == 1
    assert stats["peer_count"] == 1
