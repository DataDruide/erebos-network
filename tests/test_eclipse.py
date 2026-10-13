"""Tests fuer Eclipse-Schutz."""

import pytest

from erebos_network.eclipse_protection import (
    EclipseProtection,
    EclipseProtectionConfig,
    extract_subnet,
)
from erebos_network.discovery import DiscoveryConfig, PeerDiscovery


# --- Subnetz-Extraktion ---

def test_extract_subnet_ipv4():
    """IPv4-Subnetz wird extrahiert."""
    assert extract_subnet("192.168.1.100:8000") == "192.168.1.0/24"
    assert extract_subnet("10.0.0.5:9000") == "10.0.0.0/24"


def test_extract_subnet_loopback():
    """Loopback wird ausgenommen."""
    assert extract_subnet("127.0.0.1:8000") is None
    assert extract_subnet("127.0.0.5:9000") is None


def test_extract_subnet_invalid():
    """Ungueltige Adresse gibt None."""
    assert extract_subnet("not-an-ip") is None


# --- Eclipse-Schutz ---

def test_eclipse_accepts_first_peers():
    """Erste Peers im Subnetz werden akzeptiert."""
    ep = EclipseProtection()
    assert ep.can_accept("192.168.1.1:8000") is True
    assert ep.can_accept("192.168.1.2:8000") is True


def test_eclipse_rejects_third_peer():
    """Dritter Peer im Subnetz wird abgelehnt."""
    ep = EclipseProtection()
    ep.can_accept("192.168.1.1:8000")
    ep.can_accept("192.168.1.2:8000")
    assert ep.can_accept("192.168.1.3:8000") is False
    assert ep.stats["peers_rejected_subnet"] == 1


def test_eclipse_different_subnets():
    """Verschiedene Subnetze werden akzeptiert."""
    ep = EclipseProtection()
    assert ep.can_accept("192.168.1.1:8000") is True
    assert ep.can_accept("192.168.2.1:8000") is True
    assert ep.can_accept("10.0.0.1:8000") is True


def test_eclipse_loopback_exempt():
    """Loopback ist von Limits ausgenommen."""
    ep = EclipseProtection()
    for i in range(10):
        assert ep.can_accept(f"127.0.0.{i}:8000") is True


def test_eclipse_remove():
    """Entfernen gibt Subnetz-Slot frei."""
    ep = EclipseProtection()
    ep.can_accept("192.168.1.1:8000")
    ep.can_accept("192.168.1.2:8000")
    ep.remove("192.168.1.1:8000")
    assert ep.can_accept("192.168.1.3:8000") is True


def test_eclipse_stats():
    """Statistiken funktionieren."""
    ep = EclipseProtection()
    ep.can_accept("192.168.1.1:8000")
    ep.can_accept("192.168.1.2:8000")
    ep.can_accept("192.168.1.3:8000")  # rejected
    stats = ep.get_stats()
    assert stats["peers_accepted"] == 2
    assert stats["peers_rejected_subnet"] == 1


# --- Discovery mit Eclipse-Schutz ---

def test_discovery_eclipse_protection():
    """Discovery nutzt Eclipse-Schutz."""
    config = DiscoveryConfig(
        bootstrap_peers=[
            "192.168.1.1:8000",
            "192.168.1.2:8000",
            "192.168.1.3:8000",  # sollte abgelehnt werden
        ],
        eclipse_protection=True,
    )
    d = PeerDiscovery("127.0.0.1:9000", config)
    added = d.bootstrap()
    # Nur 2 aus demselben Subnetz
    assert added == 2
    assert d.stats["peers_rejected_eclipse"] == 1


def test_discovery_eclipse_disabled():
    """Ohne Eclipse-Schutz werden alle akzeptiert."""
    config = DiscoveryConfig(
        bootstrap_peers=[
            "192.168.1.1:8000",
            "192.168.1.2:8000",
            "192.168.1.3:8000",
        ],
        eclipse_protection=False,
    )
    d = PeerDiscovery("127.0.0.1:9000", config)
    added = d.bootstrap()
    assert added == 3
