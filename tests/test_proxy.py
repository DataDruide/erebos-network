"""Tests für den Erebos-Proxy."""

import pytest

from erebos_network.proxy import ErebosProxy
from erebos_network.sectors import SectorType


@pytest.mark.asyncio
async def test_proxy_start_stop():
    """Proxy startet und stoppt."""
    proxy = ErebosProxy()
    await proxy.start()
    stats = proxy.get_stats()
    assert stats["running"] is True

    await proxy.stop()
    stats = proxy.get_stats()
    assert stats["running"] is False


@pytest.mark.asyncio
async def test_proxy_handle_clearnet():
    """Proxy behandelt Clearnet-Anfragen."""
    proxy = ErebosProxy()
    await proxy.start()

    result = await proxy.handle_request("https://example.com")
    assert result["success"] is True
    assert result["route_type"] == "clearnet"
    assert result["sector"] == "standard"

    await proxy.stop()


@pytest.mark.asyncio
async def test_proxy_handle_i2p():
    """Proxy behandelt I2P-Anfragen."""
    proxy = ErebosProxy()
    await proxy.start()

    result = await proxy.handle_request("http://stats.i2p")
    assert result["success"] is True
    assert result["route_type"] == "eepsite"

    await proxy.stop()


@pytest.mark.asyncio
async def test_proxy_sector_override():
    """Proxy respektiert Sektor-Override."""
    proxy = ErebosProxy()
    await proxy.start()

    result = await proxy.handle_request("https://example.com", SectorType.MIXNET)
    assert result["success"] is True
    assert result["sector"] == "mixnet"
    assert result["hops"] == 7

    await proxy.stop()


@pytest.mark.asyncio
async def test_proxy_stats():
    """Proxy-Statistiken werden gezählt."""
    proxy = ErebosProxy()
    await proxy.start()

    await proxy.handle_request("https://example.com")
    await proxy.handle_request("http://stats.i2p")
    await proxy.handle_request("http://my-service.erebos")

    stats = proxy.get_stats()
    assert stats["requests_total"] == 3
    assert stats["requests_routed"] == 3

    await proxy.stop()
