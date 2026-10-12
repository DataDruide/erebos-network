"""Tests für API-Server."""

import pytest

from erebos_network.api import ErebosAPIHandler
from erebos_network.router import ErebosRouter
from erebos_network.sectors import SectorType


def test_api_handler_has_router():
    """API-Handler hat Router."""
    assert ErebosAPIHandler.router is not None


def test_api_handler_has_discovery():
    """API-Handler hat Discovery."""
    assert ErebosAPIHandler.discovery is not None


def test_api_handler_has_naming():
    """API-Handler hat Naming."""
    assert ErebosAPIHandler.naming is not None


def test_router_route_clearnet():
    """Router routet Clearnet."""
    router = ErebosRouter()
    route = router.route("https://example.com")
    assert route.route_type.value == "clearnet"


def test_router_route_i2p():
    """Router routet I2P."""
    router = ErebosRouter()
    route = router.route("http://forum.i2p")
    assert route.route_type.value == "eepsite"


def test_router_sector_override():
    """Sektor-Override funktioniert."""
    router = ErebosRouter()
    route = router.route("https://example.com", SectorType.MIXNET)
    assert route.sector.name == "mixnet"
