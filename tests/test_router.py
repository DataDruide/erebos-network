"""Tests für den Erebos-Router."""

import pytest

from erebos_network.router import ErebosRouter, RouteType
from erebos_network.sectors import SectorType, get_sector, list_sectors


def test_sectors_exist():
    """Alle Sektoren sind definiert."""
    sectors = list_sectors()
    assert len(sectors) == 4
    names = [s.name for s in sectors]
    assert "fast" in names
    assert "standard" in names
    assert "high" in names
    assert "mixnet" in names


def test_sector_properties():
    """Sektoren haben korrekte Eigenschaften."""
    fast = get_sector(SectorType.FAST)
    assert fast.hops == 2
    assert fast.anonymity == 4

    mixnet = get_sector(SectorType.MIXNET)
    assert mixnet.hops == 7
    assert mixnet.anonymity == 10
    assert mixnet.padding is True


def test_classify_clearnet():
    """Clearnet-URLs werden korrekt klassifiziert."""
    router = ErebosRouter()
    assert router.classify_target("https://example.com") == RouteType.CLEARNET
    assert router.classify_target("https://google.com") == RouteType.CLEARNET


def test_classify_i2p():
    """I2P-Adressen werden korrekt klassifiziert."""
    router = ErebosRouter()
    assert router.classify_target("http://stats.i2p") == RouteType.EEPSITE
    assert router.classify_target("http://forum.i2p") == RouteType.EEPSITE


def test_classify_erebos():
    """Erebos-Peer-Adressen werden korrekt klassifiziert."""
    router = ErebosRouter()
    assert router.classify_target("http://my-service.erebos") == RouteType.EREBOS_PEER


def test_route_clearnet():
    """Clearnet-Routing funktioniert."""
    router = ErebosRouter()
    route = router.route("https://example.com")
    assert route.route_type == RouteType.CLEARNET
    assert route.sector.name == "standard"


def test_route_i2p():
    """I2P-Routing funktioniert."""
    router = ErebosRouter()
    route = router.route("http://stats.i2p")
    assert route.route_type == RouteType.EEPSITE
    assert route.sector.name == "standard"


def test_route_peer():
    """Erebos-Peer-Routing funktioniert."""
    router = ErebosRouter()
    route = router.route("http://my-service.erebos")
    assert route.route_type == RouteType.EREBOS_PEER
    assert route.sector.name == "fast"


def test_route_with_sector_override():
    """Sektor-Override funktioniert."""
    router = ErebosRouter()
    route = router.route("https://example.com", SectorType.MIXNET)
    assert route.sector.name == "mixnet"
    assert route.sector.hops == 7


def test_proxy_selection():
    """Proxy-Auswahl funktioniert."""
    router = ErebosRouter()
    clearnet = router.route("https://example.com")
    assert router.get_proxy_for(clearnet) == "127.0.0.1:9050"

    i2p = router.route("http://stats.i2p")
    assert router.get_proxy_for(i2p) == "127.0.0.1:4444"

    peer = router.route("http://my-service.erebos")
    assert router.get_proxy_for(peer) is None


def test_stats():
    """Statistiken werden korrekt gezählt."""
    router = ErebosRouter()
    router.route("https://example.com")
    router.route("http://stats.i2p")
    router.route("http://my-service.erebos")

    stats = router.get_stats()
    assert stats["routes_total"] == 3
    assert stats["routes_clearnet"] == 1
    assert stats["routes_eepsite"] == 1
    assert stats["routes_peer"] == 1
