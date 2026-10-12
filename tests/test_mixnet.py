"""Tests für Mixnet-Layer."""

import pytest

from erebos_network.mixnet import (
    MixnetConfig,
    MixnetLayer,
    MixnetStats,
    get_mixnet_config,
)


@pytest.mark.asyncio
async def test_mixnet_basic():
    """Mixnet verarbeitet Nachricht."""
    layer = MixnetLayer()
    result = await layer.process(b"Hello, Erebos!")
    assert result is not None
    assert len(result) >= len(b"Hello, Erebos!")


@pytest.mark.asyncio
async def test_mixnet_padding():
    """Mixnet polstert Nachrichten."""
    config = MixnetConfig(padding_enabled=True, padding_block_size=1024)
    layer = MixnetLayer(config)
    result = await layer.process(b"Test")
    assert len(result) == 1024


@pytest.mark.asyncio
async def test_mixnet_no_padding():
    """Mixnet ohne Padding."""
    config = MixnetConfig(padding_enabled=False)
    layer = MixnetLayer(config)
    result = await layer.process(b"Test")
    assert result == b"Test"


@pytest.mark.asyncio
async def test_mixnet_batch():
    """Mixnet verarbeitet Batch."""
    layer = MixnetLayer()
    messages = [b"msg1", b"msg2", b"msg3"]
    results = await layer.process_batch(messages)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_mixnet_cover_traffic():
    """Mixnet erzeugt Cover-Traffic."""
    layer = MixnetLayer()
    cover = await layer.generate_cover_traffic(count=5)
    assert len(cover) == 5
    assert all(isinstance(c, bytes) for c in cover)


@pytest.mark.asyncio
async def test_mixnet_stats():
    """Mixnet-Statistiken funktionieren."""
    layer = MixnetLayer()
    await layer.process(b"Test 1")
    await layer.process(b"Test 2")
    stats = layer.get_stats()
    assert stats["messages_in"] == 2
    assert stats["messages_out"] == 2


def test_mixnet_configs():
    """Mixnet-Konfigurationen für Sektoren."""
    fast = get_mixnet_config("fast")
    assert fast.padding_enabled is False
    assert fast.cover_config.enabled is False

    mixnet = get_mixnet_config("mixnet")
    assert mixnet.padding_enabled is True
    assert mixnet.cover_config.enabled is True
    assert mixnet.batch_size == 20
