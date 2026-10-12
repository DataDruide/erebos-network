"""Tests für Payment-System."""

import pytest

from erebos_network.payment import (
    Order,
    PaymentPurpose,
    PaymentSystem,
    ServiceOffer,
)
from erebos_network.wallet import MoneroWallet


def test_payment_system_init():
    """Payment-System initialisiert."""
    ps = PaymentSystem()
    assert ps.offer_count == 0
    assert ps.order_count == 0


def test_create_offer():
    """Angebot wird erstellt."""
    ps = PaymentSystem()
    offer = ps.create_offer(
        offer_id="o1",
        provider_peer_id="peer1",
        title="Test Service",
        description="Beschreibung",
        price_xmr=0.5,
    )
    assert offer.price_xmr == 0.5
    assert ps.offer_count == 1


def test_create_offer_invalid_price():
    """Negativer Preis wirft Fehler."""
    ps = PaymentSystem()
    with pytest.raises(ValueError):
        ps.create_offer("o1", "peer1", "T", "D", -1.0)


def test_create_order():
    """Bestellung wird erstellt."""
    ps = PaymentSystem()
    ps.create_offer("o1", "peer1", "Test", "D", 0.5)
    order = ps.create_order("ord1", "o1", "buyer1")
    assert order.amount_xmr == 0.5
    assert order.status == "created"
    assert ps.order_count == 1


def test_create_order_unknown_offer():
    """Unbekanntes Angebot wirft Fehler."""
    ps = PaymentSystem()
    with pytest.raises(ValueError):
        ps.create_order("ord1", "unknown", "buyer1")


def test_pay_order():
    """Bestellung wird bezahlt."""
    wallet = MoneroWallet()
    wallet.receive(10.0)
    ps = PaymentSystem(wallet)

    ps.create_offer("o1", "peer1", "Test", "D", 1.0)
    ps.create_order("ord1", "o1", "buyer1")
    assert ps.pay_order("ord1") is True

    order = ps.get_order("ord1")
    assert order.status == "paid"


def test_complete_order():
    """Bestellung wird abgeschlossen."""
    wallet = MoneroWallet()
    wallet.receive(10.0)
    ps = PaymentSystem(wallet)

    ps.create_offer("o1", "peer1", "Test", "D", 1.0)
    ps.create_order("ord1", "o1", "buyer1")
    ps.pay_order("ord1")
    assert ps.complete_order("ord1") is True
    assert ps.get_order("ord1").status == "completed"


def test_list_offers_by_purpose():
    """Angebote nach Zweck filtern."""
    ps = PaymentSystem()
    ps.create_offer("o1", "p1", "Job", "D", 1.0, PaymentPurpose.JOB)
    ps.create_offer("o2", "p2", "Service", "D", 2.0, PaymentPurpose.SERVICE)

    jobs = ps.list_offers(PaymentPurpose.JOB)
    assert len(jobs) == 1
    assert jobs[0].offer_id == "o1"


def test_payment_stats():
    """Payment-Statistiken."""
    wallet = MoneroWallet()
    wallet.receive(10.0)
    ps = PaymentSystem(wallet)

    ps.create_offer("o1", "peer1", "Test", "D", 1.0)
    ps.create_order("ord1", "o1", "buyer1")
    ps.pay_order("ord1")

    stats = ps.get_stats()
    assert stats["offers_created"] == 1
    assert stats["orders_created"] == 1
    assert stats["orders_paid"] == 1
    assert stats["total_volume_xmr"] == 1.0
