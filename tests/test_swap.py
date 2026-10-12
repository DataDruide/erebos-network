"""Tests für Atomic-Swap."""

import pytest

from erebos_network.swap import AtomicSwap, SwapStatus


def test_swap_init():
    """Atomic-Swap initialisiert."""
    s = AtomicSwap()
    assert s.offer_count == 0


def test_create_offer():
    """Swap-Angebot wird erstellt."""
    s = AtomicSwap()
    offer = s.create_offer(
        initiator_peer_id="peer1",
        offer_amount_xmr=1.0,
        request_amount_xmr=2.0,
    )
    assert offer.offer_amount_xmr == 1.0
    assert offer.request_amount_xmr == 2.0
    assert offer.status == SwapStatus.INITIATED


def test_create_offer_invalid():
    """Ungültige Beträge werfen Fehler."""
    s = AtomicSwap()
    with pytest.raises(ValueError):
        s.create_offer("peer1", 0.0, 1.0)
    with pytest.raises(ValueError):
        s.create_offer("peer1", 1.0, -1.0)


def test_join_swap():
    """Gegenpartei tritt bei."""
    s = AtomicSwap()
    offer = s.create_offer("peer1", 1.0, 2.0)
    assert s.join_swap(offer.swap_id, "peer2") is True
    assert s.get_offer(offer.swap_id).status == SwapStatus.COUNTERPARTY_JOINED


def test_join_unknown_swap():
    """Unbekannter Swap wirft Fehler."""
    s = AtomicSwap()
    with pytest.raises(ValueError):
        s.join_swap("unknown", "peer2")


def test_execute_swap():
    """Swap wird ausgeführt."""
    s = AtomicSwap()
    offer = s.create_offer("peer1", 1.0, 2.0)
    s.join_swap(offer.swap_id, "peer2")
    assert s.execute_swap(offer.swap_id) is True
    assert s.get_offer(offer.swap_id).status == SwapStatus.REDEEMED


def test_execute_unjoined_swap():
    """Swap ohne Gegenpartei schlägt fehl."""
    s = AtomicSwap()
    offer = s.create_offer("peer1", 1.0, 2.0)
    assert s.execute_swap(offer.swap_id) is False


def test_swap_stats():
    """Swap-Statistiken."""
    s = AtomicSwap()
    offer = s.create_offer("peer1", 1.0, 2.0)
    s.join_swap(offer.swap_id, "peer2")
    s.execute_swap(offer.swap_id)
    stats = s.get_stats()
    assert stats["offers_created"] == 1
    assert stats["swaps_completed"] == 1
