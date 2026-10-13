"""Tests fuer Monero-Reorg-Schutz."""

import pytest

from erebos_network.reorg_protection import (
    MoneroReorgProtection,
    ReorgConfig,
    ReorgStatus,
)


def test_reorg_init():
    """Reorg-Schutz initialisiert."""
    rp = MoneroReorgProtection()
    assert rp.current_height == 0
    assert rp.stats["reorgs_detected"] == 0


def test_reorg_update_chain():
    """Chain-Update funktioniert."""
    rp = MoneroReorgProtection()
    assert rp.update_chain(100, "hash100") is False
    assert rp.current_height == 100


def test_reorg_detection():
    """Reorg wird erkannt."""
    rp = MoneroReorgProtection()
    rp.update_chain(100, "hash100")
    # Height sinkt -> Reorg
    assert rp.update_chain(90, "hash90") is True
    assert rp.stats["reorgs_detected"] == 1


def test_register_payment():
    """Payment wird registriert."""
    rp = MoneroReorgProtection()
    rp.update_chain(100, "hash100")
    p = rp.register_payment("tx1", 1.0, 5, 100, "hash100")
    assert p.tx_hash == "tx1"
    assert p.status == ReorgStatus.PENDING


def test_payment_required_confirmations():
    """Benoetigte Bestaetigungen je nach Wert."""
    rp = MoneroReorgProtection()
    rp.update_chain(100, "hash100")

    p_low = rp.register_payment("tx1", 1.0, 5, 100, "hash100")
    assert p_low.required_confirmations == 20

    p_high = rp.register_payment("tx2", 50.0, 5, 100, "hash100")
    assert p_high.required_confirmations == 30


def test_payment_confirmed():
    """Payment wird nach genug Bestaetigungen bestaetigt."""
    rp = MoneroReorgProtection()
    rp.update_chain(100, "hash100")
    rp.register_payment("tx1", 1.0, 5, 100, "hash100")

    status = rp.update_confirmations("tx1", 25, 100, "hash100")
    assert status == ReorgStatus.OK
    assert rp.is_payment_safe("tx1") is True


def test_payment_not_enough_confirmations():
    """Payment bleibt PENDING bei zu wenig Bestaetigungen."""
    rp = MoneroReorgProtection()
    rp.update_chain(100, "hash100")
    rp.register_payment("tx1", 1.0, 5, 100, "hash100")

    status = rp.update_confirmations("tx1", 10, 100, "hash100")
    assert status == ReorgStatus.PENDING
    assert rp.is_payment_safe("tx1") is False


def test_reorg_invalidates_payment():
    """Reorg invalidiert betroffene Payments."""
    rp = MoneroReorgProtection()
    rp.update_chain(100, "hash100")
    rp.register_payment("tx1", 1.0, 5, 100, "hash100")
    rp.update_confirmations("tx1", 25, 100, "hash100")
    assert rp.is_payment_safe("tx1") is True

    # Reorg auf Height 90
    rp.update_chain(90, "hash90")

    payment = rp.get_payment("tx1")
    assert payment.status == ReorgStatus.INVALIDATED
    assert rp.stats["payments_invalidated"] == 1


def test_block_hash_mismatch():
    """Block-Hash-Mismatch invalidiert Payment."""
    rp = MoneroReorgProtection()
    rp.update_chain(100, "hash100")
    rp.register_payment("tx1", 1.0, 5, 100, "hash100")

    # Anderer Hash bei gleicher Height
    status = rp.update_confirmations("tx1", 25, 100, "DIFFERENT_HASH")
    assert status == ReorgStatus.INVALIDATED


def test_reorg_stats():
    """Reorg-Statistiken."""
    rp = MoneroReorgProtection()
    rp.update_chain(100, "hash100")
    rp.register_payment("tx1", 1.0, 5, 100, "hash100")
    rp.update_chain(90, "hash90")

    stats = rp.get_stats()
    assert stats["reorgs_detected"] == 1
    assert stats["payments_invalidated"] == 1
    assert stats["current_height"] == 90
