"""Tests für Naming-Service."""

import pytest

from erebos_network.naming import (
    NamingService,
    domain_to_peer_id,
    is_erebos_domain,
    parse_erebos_domain,
)


def test_is_erebos_domain():
    """Erebos-Domains werden erkannt."""
    assert is_erebos_domain("forum.erebos") is True
    assert is_erebos_domain("my-service.erebos") is True
    assert is_erebos_domain("example.com") is False


def test_parse_erebos_domain():
    """Domain-Name wird extrahiert."""
    assert parse_erebos_domain("forum.erebos") == "forum"
    assert parse_erebos_domain("my-service.erebos") == "my-service"
    assert parse_erebos_domain("example.com") is None


def test_domain_to_peer_id():
    """Domain wird zu Peer-ID."""
    id1 = domain_to_peer_id("forum.erebos")
    id2 = domain_to_peer_id("forum.erebos")
    assert id1 == id2
    assert len(id1) == 64


def test_naming_register():
    """Domain wird registriert."""
    ns = NamingService()
    record = ns.register("forum", "127.0.0.1:8000")
    assert record.name == "forum"
    assert record.full_domain == "forum.erebos"
    assert ns.count == 1


def test_naming_resolve():
    """Domain wird aufgelöst."""
    ns = NamingService()
    ns.register("forum", "127.0.0.1:8000")
    record = ns.resolve("forum.erebos")
    assert record is not None
    assert record.address == "127.0.0.1:8000"


def test_naming_invalid():
    """Ungültige Domain wirft Fehler."""
    ns = NamingService()
    with pytest.raises(ValueError):
        ns.register("UPPERCASE!", "127.0.0.1:8000")


def test_naming_unregister():
    """Domain wird entfernt."""
    ns = NamingService()
    ns.register("forum", "127.0.0.1:8000")
    assert ns.unregister("forum.erebos") is True
    assert ns.count == 0
