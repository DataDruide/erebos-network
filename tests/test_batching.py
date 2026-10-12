"""Tests für Batching."""

import pytest

from erebos_network.batching import Batch, Batcher


def test_batch_basic():
    """Batch funktioniert."""
    batch = Batch()
    assert batch.size == 0

    batch.add(b"msg1")
    batch.add(b"msg2")
    assert batch.size == 2

    batch.clear()
    assert batch.size == 0


@pytest.mark.asyncio
async def test_batcher_under_limit():
    """Batcher unter Limit gibt None zurück."""
    batcher = Batcher(max_size=5)
    for i in range(4):
        result = await batcher.add(f"msg{i}".encode())
        assert result is None
    assert batcher.pending == 4


@pytest.mark.asyncio
async def test_batcher_full():
    """Batcher gibt Batch zurück wenn voll."""
    batcher = Batcher(max_size=3)
    await batcher.add(b"msg1")
    await batcher.add(b"msg2")
    result = await batcher.add(b"msg3")
    assert result is not None
    assert result.size == 3


@pytest.mark.asyncio
async def test_batcher_flush():
    """Batcher kann geflusht werden."""
    batcher = Batcher(max_size=10)
    await batcher.add(b"msg1")
    await batcher.add(b"msg2")
    batch = await batcher.flush()
    assert batch is not None
    assert batch.size == 2
    assert batcher.pending == 0


@pytest.mark.asyncio
async def test_batcher_counter():
    """Batcher zählt Batches."""
    batcher = Batcher(max_size=2)
    await batcher.add(b"a")
    await batcher.add(b"b")
    assert batcher.batches_created == 1
    await batcher.add(b"c")
    await batcher.add(b"d")
    assert batcher.batches_created == 2
