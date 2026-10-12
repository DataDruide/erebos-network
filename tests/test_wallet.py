"""Tests für Monero-Wallet-Integration."""

import pytest

from erebos_network.wallet import (
    MoneroWallet,
    PaymentRequest,
    PaymentStatus,
)


def test_wallet_init():
    """Wallet initialisiert."""
    w = MoneroWallet()
    assert w.address.startswith("4")
    assert len(w.address) == 65  # Simulation: 1 + 64 Hex-Zeichen
    assert w.request_count == 0


def test_wallet_info():
    """Wallet-Info funktioniert."""
    w = MoneroWallet()
    info = w.get_info()
    assert info.balance_xmr == 0.0
    assert info.address == w.address


def test_create_request():
    """Zahlungsanfrage wird erstellt."""
    w = MoneroWallet()
    req = w.create_request(
        amount_xmr=0.5,
        recipient_address="4abc...",
        memo="Test",
    )
    assert req.amount_xmr == 0.5
    assert req.memo == "Test"
    assert req.status == PaymentStatus.PENDING
    assert w.request_count == 1


def test_create_request_invalid():
    """Ungültiger Betrag wirft Fehler."""
    w = MoneroWallet()
    with pytest.raises(ValueError):
        w.create_request(amount_xmr=0.0, recipient_address="4abc")
    with pytest.raises(ValueError):
        w.create_request(amount_xmr=-1.0, recipient_address="4abc")


def test_receive():
    """Zahlung empfangen."""
    w = MoneroWallet()
    w.receive(1.5, memo="Test")
    info = w.get_info()
    assert info.balance_xmr == 1.5


def test_pay_insufficient_balance():
    """Zahlung ohne Guthaben schlägt fehl."""
    w = MoneroWallet()
    req = w.create_request(amount_xmr=10.0, recipient_address="4abc")
    assert w.pay(req.request_id) is False
    assert w.get_request(req.request_id).status == PaymentStatus.FAILED


def test_pay_success():
    """Zahlung mit Guthaben funktioniert."""
    w = MoneroWallet()
    w.receive(10.0)
    req = w.create_request(amount_xmr=1.0, recipient_address="4abc")
    assert w.pay(req.request_id) is True
    assert w.get_request(req.request_id).status == PaymentStatus.CONFIRMED
    assert w.get_info().balance_xmr == 9.0


def test_list_requests():
    """Anfragen auflisten."""
    w = MoneroWallet()
    w.create_request(1.0, "4abc")
    w.create_request(2.0, "4def")
    pending = w.list_requests(PaymentStatus.PENDING)
    assert len(pending) == 2


def test_wallet_stats():
    """Wallet-Statistiken."""
    w = MoneroWallet()
    w.receive(5.0)
    w.create_request(1.0, "4abc")
    stats = w.get_stats()
    assert stats["balance_xmr"] == 5.0
    assert stats["requests_total"] == 1
