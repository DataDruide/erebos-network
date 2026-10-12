"""Tests für Erebos-Peer."""

import pytest

from erebos_network.peer import ErebosPeer, PeerConfig


@pytest.mark.asyncio
async def test_peer_start_stop():
    """Peer startet und stoppt."""
    config = PeerConfig(address="127.0.0.1:9000")
    peer = ErebosPeer(config)
    await peer.start()
    stats = peer.get_stats()
    assert stats["running"] is True
    await peer.stop()
    stats = peer.get_stats()
    assert stats["running"] is False


@pytest.mark.asyncio
async def test_peer_register_domain():
    """Peer registriert Domain."""
    config = PeerConfig(address="127.0.0.1:9000")
    peer = ErebosPeer(config)
    await peer.start()
    domain = peer.register_domain("forum")
    assert domain == "forum.erebos"
    await peer.stop()


@pytest.mark.asyncio
async def test_peer_resolve_domain():
    """Peer löst Domain auf."""
    config = PeerConfig(address="127.0.0.1:9000")
    peer = ErebosPeer(config)
    await peer.start()
    peer.register_domain("forum")
    address = peer.resolve_domain("forum.erebos")
    assert address == "127.0.0.1:9000"
    await peer.stop()


@pytest.mark.asyncio
async def test_peer_bootstrap():
    """Peer bootstrappt über andere Peers."""
    config = PeerConfig(
        address="127.0.0.1:9000",
        bootstrap_peers=["127.0.0.1:9001", "127.0.0.1:9002"],
    )
    peer = ErebosPeer(config)
    await peer.start()
    stats = peer.get_stats()
    assert stats["discovery"]["peer_count"] == 2
    await peer.stop()
