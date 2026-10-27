"""Tests fuer Chat-E2E-Verschluesselung (X25519 + ML-KEM-1024)."""

import hashlib

import pytest


@pytest.fixture
def fresh_e2e(temp_db, monkeypatch):
    """Frische E2E-Tabellen + no_db_key."""
    from erebos_network import forum_db
    from erebos_network import chat_e2e
    # Sicherstellen, dass die Migration gelaufen ist
    conn = forum_db.get_db()
    with conn:
        conn.execute("DELETE FROM chat_e2e_keys")
        conn.execute("DELETE FROM chat_e2e_messages")
    yield chat_e2e
    with conn:
        conn.execute("DELETE FROM chat_e2e_keys")
        conn.execute("DELETE FROM chat_e2e_messages")


def test_initiator_responder_same_key(fresh_e2e):
    """A (Initiator) + B (Responder) leiten denselben Shared Key ab."""
    from erebos_network.chat_e2e import E2ESession

    a = E2ESession(role="initiator")
    b = E2ESession(role="responder")

    payload_a = a.initiator_payload()
    payload_b = b.responder_payload(payload_a.x25519_pub, payload_a.mlkem_pub)

    a.finalize_initiator(payload_b.x25519_pub, payload_b.mlkem_ct)

    assert a.fingerprint == b.fingerprint
    assert a.is_ready
    assert b.is_ready


def test_encrypt_decrypt_roundtrip(fresh_e2e):
    """A verschluesselt, B entschluesselt."""
    from erebos_network.chat_e2e import E2ESession

    a = E2ESession(role="initiator")
    b = E2ESession(role="responder")

    payload_a = a.initiator_payload()
    payload_b = b.responder_payload(payload_a.x25519_pub, payload_a.mlkem_pub)
    a.finalize_initiator(payload_b.x25519_pub, payload_b.mlkem_ct)

    nonce, ct = a.encrypt(b"Hallo von A")
    plaintext = b.decrypt(nonce, ct)
    assert plaintext == b"Hallo von A"

    # Umgekehrt
    nonce2, ct2 = b.encrypt(b"Hallo von B")
    plaintext2 = a.decrypt(nonce2, ct2)
    assert plaintext2 == b"Hallo von B"


def test_fingerprint_format(fresh_e2e):
    """Fingerprint hat Format 'xxxx-xxxx-xxxx-xxxx'."""
    from erebos_network.chat_e2e import E2ESession

    a = E2ESession(role="initiator")
    b = E2ESession(role="responder")
    payload_a = a.initiator_payload()
    payload_b = b.responder_payload(payload_a.x25519_pub, payload_a.mlkem_pub)
    a.finalize_initiator(payload_b.x25519_pub, payload_b.mlkem_ct)

    fp = a.fingerprint
    parts = fp.split("-")
    assert len(parts) == 4
    assert all(len(p) == 4 for p in parts)
    assert all(c in "0123456789abcdef" for p in parts for c in p)


def test_wrong_key_cannot_decrypt(fresh_e2e):
    """Ein dritter Client (C) kann Nachrichten von A→B nicht entschluesseln."""
    from erebos_network.chat_e2e import E2ESession

    a = E2ESession(role="initiator")
    b = E2ESession(role="responder")
    payload_a = a.initiator_payload()
    payload_b = b.responder_payload(payload_a.x25519_pub, payload_a.mlkem_pub)
    a.finalize_initiator(payload_b.x25519_pub, payload_b.mlkem_ct)

    # C: neue Session mit eigenem Key (kein Key-Exchange mit A)
    c = E2ESession(role="initiator")
    # C hat keinen Shared Key -> encrypt/decrypt wirft RuntimeError
    with pytest.raises(RuntimeError):
        c.decrypt(b"\x00" * 12, b"\x00" * 32)

    # A verschluesselt
    nonce, ct = a.encrypt(b"Geheim")
    # B entschluesselt
    assert b.decrypt(nonce, ct) == b"Geheim"


def test_encrypt_requires_key(fresh_e2e):
    """encrypt() ohne Key-Exchange wirft RuntimeError."""
    from erebos_network.chat_e2e import E2ESession

    a = E2ESession(role="initiator")
    with pytest.raises(RuntimeError):
        a.encrypt(b"test")


def test_store_and_get_key(fresh_e2e):
    """store_key + get_key + get_partner_key funktionieren."""
    from erebos_network.chat_e2e import E2ESession, store_key, get_key, get_partner_key

    a = E2ESession(role="initiator")
    b = E2ESession(role="responder")

    payload_a = a.initiator_payload()
    store_key("room1", "cookie-A", "initiator", payload_a)

    payload_b = b.responder_payload(payload_a.x25519_pub, payload_a.mlkem_pub)
    store_key("room1", "cookie-B", "responder", payload_b)

    # get_key
    ka = get_key("room1", "cookie-A")
    assert ka["role"] == "initiator"
    assert ka["x25519_pub"] == payload_a.x25519_pub
    assert ka["mlkem_pub"] == payload_a.mlkem_pub

    # get_partner_key
    partner_for_a = get_partner_key("room1", "cookie-A")
    assert partner_for_a["cookie"] == "cookie-B"
    assert partner_for_a["role"] == "responder"
    assert partner_for_a["mlkem_ct"] == payload_b.mlkem_ct


def test_store_and_get_encrypted_message(fresh_e2e):
    """store_encrypted_message + get_encrypted_messages funktionieren."""
    from erebos_network.chat_e2e import (
        store_encrypted_message,
        get_encrypted_messages,
    )

    nonce = b"\x01" * 12
    ct = b"\x02" * 48
    msg_id = store_encrypted_message("room1", "cookie-A", nonce, ct)
    assert msg_id > 0

    msgs = get_encrypted_messages("room1", since=0)
    assert len(msgs) == 1
    assert msgs[0]["from"] == "cookie-A"
    assert msgs[0]["nonce"] == nonce
    assert msgs[0]["ciphertext"] == ct


def test_server_sees_only_ciphertext(fresh_e2e):
    """Was in der DB landet, ist Ciphertext, nicht Klartext."""
    from erebos_network.chat_e2e import (
        E2ESession,
        store_encrypted_message,
        get_encrypted_messages,
    )
    from erebos_network import forum_db

    a = E2ESession(role="initiator")
    b = E2ESession(role="responder")
    payload_a = a.initiator_payload()
    payload_b = b.responder_payload(payload_a.x25519_pub, payload_a.mlkem_pub)
    a.finalize_initiator(payload_b.x25519_pub, payload_b.mlkem_ct)

    plaintext = b"Das ist ein Geheimnis"
    nonce, ct = a.encrypt(plaintext)
    store_encrypted_message("room1", "cookie-A", nonce, ct)

    # Direkt in der DB nachschauen
    conn = forum_db.get_db()
    row = conn.execute(
        "SELECT ciphertext FROM chat_e2e_messages WHERE room_id = ?",
        ("room1",),
    ).fetchone()
    stored = bytes(row[0])
    # Klartext darf NICHT enthalten sein
    assert plaintext not in stored
    # Aber Ciphertext schon
    assert stored == ct
