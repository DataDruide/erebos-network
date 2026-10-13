"""Tests fuer Flow-Splitting."""

import pytest

from erebos_network.flow_splitting import (
    CoverInjector,
    FlowChunk,
    FlowSplittingDefense,
    FlowSplitter,
    SplitConfig,
)


# --- FlowSplitter ---

def test_splitter_init():
    """Splitter initialisiert."""
    s = FlowSplitter()
    assert s.stats["chunks_created"] == 0


def test_splitter_splits_data():
    """Splitter teilt Daten auf."""
    s = FlowSplitter()
    data = b"x" * 1000
    chunks = s.split(data, chunk_size=256)
    assert len(chunks) == 4
    assert s.stats["chunks_created"] == 4


def test_splitter_uses_gateways():
    """Splitter nutzt mehrere Gateways."""
    config = SplitConfig(num_gateways=4, markov_p=0.5)
    s = FlowSplitter(config)
    data = b"x" * 1000
    chunks = s.split(data, chunk_size=64)
    gateways = {c.gateway_id for c in chunks}
    # Bei p=0.5 sollten mehrere Gateways genutzt werden
    assert len(gateways) >= 2


def test_splitter_reassemble():
    """Splitter reassembelt korrekt."""
    s = FlowSplitter()
    data = b"Hello, Erebos! " * 50
    chunks = s.split(data, chunk_size=64)
    reassembled = s.reassemble(chunks)
    assert reassembled == data


def test_splitter_single_gateway():
    """Splitter mit nur einem Gateway."""
    config = SplitConfig(num_gateways=1)
    s = FlowSplitter(config)
    data = b"x" * 100
    chunks = s.split(data, chunk_size=32)
    gateways = {c.gateway_id for c in chunks}
    assert len(gateways) == 1


def test_splitter_stats():
    """Splitter-Statistiken."""
    s = FlowSplitter()
    s.split(b"x" * 500, chunk_size=100)
    stats = s.get_stats()
    assert stats["chunks_created"] == 5
    assert stats["bytes_split"] == 500


# --- CoverInjector ---

def test_injector_init():
    """Injector initialisiert."""
    i = CoverInjector()
    assert i.stats["cover_chunks"] == 0


def test_injector_adds_cover():
    """Injector fuegt Cover hinzu."""
    config = SplitConfig(cover_multiplier=2.0)
    i = CoverInjector(config)
    chunks = [
        FlowChunk("c1", 0, b"x" * 100, 1),
        FlowChunk("c2", 1, b"y" * 100, 2),
    ]
    result = i.inject(chunks)
    # 2 echte + 4 Cover = 6
    assert len(result) == 6
    cover_count = sum(1 for c in result if c.is_cover)
    assert cover_count == 4


def test_injector_zero_cover():
    """Injector mit I=0 fuegt nichts hinzu."""
    config = SplitConfig(cover_multiplier=0.0)
    i = CoverInjector(config)
    chunks = [FlowChunk("c1", 0, b"x" * 100, 1)]
    result = i.inject(chunks)
    assert len(result) == 1


def test_injector_marks_cover():
    """Injector markiert Cover-Chunks."""
    config = SplitConfig(cover_multiplier=1.0)
    i = CoverInjector(config)
    chunks = [FlowChunk("c1", 0, b"x" * 100, 1)]
    result = i.inject(chunks)
    cover = [c for c in result if c.is_cover]
    assert len(cover) >= 1


def test_injector_stats():
    """Injector-Statistiken."""
    config = SplitConfig(cover_multiplier=2.0)
    i = CoverInjector(config)
    chunks = [FlowChunk(f"c{i}", 0, b"x" * 100, i) for i in range(5)]
    i.inject(chunks)
    stats = i.get_stats()
    assert stats["cover_chunks"] == 10
    assert stats["cover_multiplier"] == 2.0


def test_injector_empty():
    """Injector mit leerer Liste."""
    i = CoverInjector()
    result = i.inject([])
    assert result == []


# --- FlowSplittingDefense ---

def test_defense_process():
    """Defense verarbeitet Daten."""
    d = FlowSplittingDefense()
    data = b"x" * 1000
    chunks = d.process(data)
    assert len(chunks) > 0


def test_defense_stats():
    """Defense-Statistiken."""
    d = FlowSplittingDefense()
    d.process(b"x" * 500)
    stats = d.get_stats()
    assert "splitter" in stats
    assert "injector" in stats


def test_defense_default_config():
    """Defense nutzt Standard-Config (S=4, I=2.0)."""
    d = FlowSplittingDefense()
    assert d.config.num_gateways == 4
    assert d.config.cover_multiplier == 2.0


def test_defense_custom_config():
    """Defense akzeptiert Custom-Config."""
    config = SplitConfig(num_gateways=8, cover_multiplier=4.0)
    d = FlowSplittingDefense(config)
    assert d.config.num_gateways == 8
    assert d.config.cover_multiplier == 4.0
