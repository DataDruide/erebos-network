"""Tests fuer Forward Secrecy (Ratchet)."""

import pytest
from erebos_network.chat_e2e import (
    E2ESession,
    RATCHET_INTERVAL,
    store_encrypted_message,
    get_encrypted_messages,
)


@pytest.fixture
def fresh_e2e(temp_db, monkeypatch):
    from erebos_network import forum_db
    from erebos_network import chat_e2e
    conn = forum_db.get_db()
    with conn:
        conn.execute("DELETE FROM chat_e2e_keys")
        conn.execute("DELETE FROM chat_e2e_messages")
    yield chat_e2e
    with conn:
        conn.execute("DELETE FROM chat_e2e_keys")
        conn.execute("DELETE FROM chat_e2e_messages")


def _make_pair():
    a = E2ESession(role="initiator")
    b = E2ESession(role="responder")
    payload_a = a.initiator_payload()
    payload_b = b.responder_payload(payload_a.x25519_pub, payload_a.mlkem_pub)
    a.finalize_initiator(payload_b.x25519_pub, payload_b.mlkem_ct)
    return a, b


def test_ratchet_increments_epoch(fresh_e2e):
    a, b = _make_pair()
    assert a.epoch == 0
    assert b.epoch == 0
    a.ratchet()
    assert a.epoch == 1
    assert b.epoch == 0  # b ratcheted nicht automatisch


def test_ratchet_changes_key(fresh_e2e):
    a, b = _make_pair()
    key_before = a._shared_key
    a.ratchet()
    assert a._shared_key != key_before


def test_ratchet_after_interval(fresh_e2e):
    a, b = _make_pair()
    for i in range(RATCHET_INTERVAL):
        a.encrypt(f"msg {i}".encode())
    assert a.epoch == 1  # Nach RATCHET_INTERVAL Nachrichten
    # Naechste Nachricht ist mit neuem Key
    nonce, ct = a.encrypt(b"nach ratchet")
    assert a.epoch == 1


def test_store_and_get_with_epoch(fresh_e2e):
    nonce = b"\x01" * 12
    ct = b"\x02" * 48
    store_encrypted_message("room1", "cookie-A", nonce, ct, key_epoch=3)
    msgs = get_encrypted_messages("room1", since=0)
    assert len(msgs) == 1
    assert msgs[0]["key_epoch"] == 3
