"""Tests fuer Dandelion++ Verstaerkung."""

import time

import pytest

from erebos_network.dandelion_plus import (
    CoverTransactionGenerator,
    DandelionConfig,
    DandelionPhase,
    DandelionPlusManager,
    DecoyStrategy,
    EmbargoRandomizer,
    FCMPReadyInterface,
    OSPEADDecoySampler,
    PeerFallback,
    Transaction,
)


# --- EmbargoRandomizer ---

def test_embargo_init():
    """Embargo initialisiert."""
    e = EmbargoRandomizer()
    assert e.stats["timeouts_scheduled"] == 0


def test_embargo_schedules():
    """Embargo plant Timeout."""
    e = EmbargoRandomizer()
    timeout = e.schedule_embargo()
    assert 5.0 <= timeout <= 180.0


def test_embargo_poisson_distribution():
    """Embargo nutzt Poisson-Verteilung."""
    e = EmbargoRandomizer()
    timeouts = [e.schedule_embargo() for _ in range(100)]
    # Poisson: viele kurze, wenige lange
    short = sum(1 for t in timeouts if t < 39.0)
    assert short > 50  # Mehr als die Haelfte sollte unter Mean sein


def test_embargo_avg():
    """Embargo-Durchschnitt."""
    e = EmbargoRandomizer()
    for _ in range(100):
        e.schedule_embargo()
    assert 20.0 <= e.avg_timeout <= 80.0


# --- OSPEADDecoySampler ---

def test_ospead_init():
    """OSPEAD initialisiert."""
    s = OSPEADDecoySampler()
    assert s.stats["decoys_sampled"] == 0


def test_ospead_samples():
    """OSPEAD waehlt Decoys."""
    s = OSPEADDecoySampler()
    decoys = s.sample_decoys(real_index=0, ring_size=16)
    assert len(decoys) == 16
    assert 0 in decoys


def test_ospead_different_real():
    """OSPEAD mit verschiedenen Real-Indices."""
    s = OSPEADDecoySampler()
    d1 = s.sample_decoys(real_index=5, ring_size=16)
    d2 = s.sample_decoys(real_index=10, ring_size=16)
    assert 5 in d1
    assert 10 in d2


def test_ospead_stats():
    """OSPEAD-Statistiken."""
    s = OSPEADDecoySampler()
    s.sample_decoys(0)
    stats = s.get_stats()
    assert stats["decoys_sampled"] == 1


# --- PeerFallback ---

def test_peer_fallback_init():
    """Peer-Fallback initialisiert."""
    p = PeerFallback()
    assert p.stats["fallbacks_used"] == 0


def test_peer_fallback_with_height():
    """Peer-Fallback mit Height-Peers."""
    p = PeerFallback()
    peer = p.select_stem_peer(
        peers_with_height=["peer1", "peer2"],
        peers_without_height=["peer3"],
    )
    assert peer in ["peer1", "peer2"]
    assert p.stats["fallbacks_used"] == 0


def test_peer_fallback_without_height():
    """Peer-Fallback ohne Height-Peers."""
    p = PeerFallback()
    peer = p.select_stem_peer(
        peers_with_height=[],
        peers_without_height=["peer3", "peer4"],
    )
    assert peer in ["peer3", "peer4"]
    assert p.stats["fallbacks_used"] == 1
    assert p.stats["degradations_prevented"] == 1


def test_peer_fallback_disabled():
    """Peer-Fallback deaktiviert."""
    config = DandelionConfig(peer_fallback_enabled=False)
    p = PeerFallback(config)
    peer = p.select_stem_peer(
        peers_with_height=[],
        peers_without_height=["peer3"],
    )
    assert peer is None


# --- CoverTransactionGenerator ---

def test_cover_init():
    """Cover-Generator initialisiert."""
    c = CoverTransactionGenerator()
    assert c.stats["cover_txs_generated"] == 0


def test_cover_generates():
    """Cover-Tx wird generiert."""
    c = CoverTransactionGenerator()
    tx = c.generate()
    assert tx.is_cover is True
    assert len(tx.data) > 0


def test_cover_rate():
    """Cover-Rate funktioniert."""
    config = DandelionConfig(cover_tx_rate=1.0)
    c = CoverTransactionGenerator(config)
    assert c.should_generate() is True


# --- FCMPReadyInterface ---

def test_fcmp_init():
    """FCMP-Interface initialisiert."""
    f = FCMPReadyInterface()
    assert f.stats["fcmp_ready"] is True


def test_fcmp_anonymity_set():
    """FCMP-Anonymitaets-Set."""
    f = FCMPReadyInterface()
    assert f.get_anonymity_set_size() == 100_000_000


def test_fcmp_disabled():
    """FCMP deaktiviert."""
    config = DandelionConfig(fcmp_ready=False)
    f = FCMPReadyInterface(config)
    assert f.get_anonymity_set_size() == 16


# --- DandelionPlusManager ---

def test_manager_init():
    """Manager initialisiert."""
    m = DandelionPlusManager()
    assert m.stats["transactions_processed"] == 0


def test_manager_process():
    """Manager verarbeitet Tx."""
    m = DandelionPlusManager()
    tx = m.process_transaction("tx1", b"data")
    assert tx.tx_id == "tx1"
    assert tx.phase in [DandelionPhase.STEM, DandelionPhase.FLUFF]
    assert tx.embargo_at > time.time()


def test_manager_stem_probability():
    """Manager nutzt Stem-Wahrscheinlichkeit."""
    config = DandelionConfig(stem_probability=1.0)
    m = DandelionPlusManager(config)
    for i in range(10):
        m.process_transaction(f"tx{i}", b"data")
    assert m.stats["stem_transactions"] == 10
    assert m.stats["fluff_transactions"] == 0


def test_manager_fluff_probability():
    """Manager nutzt Fluff-Wahrscheinlichkeit."""
    config = DandelionConfig(stem_probability=0.0)
    m = DandelionPlusManager(config)
    for i in range(10):
        m.process_transaction(f"tx{i}", b"data")
    assert m.stats["stem_transactions"] == 0
    assert m.stats["fluff_transactions"] == 10


def test_manager_stats():
    """Manager-Statistiken."""
    m = DandelionPlusManager()
    m.process_transaction("tx1", b"data")
    stats = m.get_stats()
    assert "embargo" in stats
    assert "decoys" in stats
    assert "peer_fallback" in stats
    assert "cover" in stats
    assert "fcmp" in stats
