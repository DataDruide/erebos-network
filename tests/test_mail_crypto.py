"""Tests for sign_mail, verify_mail, verify_mail_with_status.

Ergaenzt test_crypto.py (klassische PQ-Krypto) um die Mail-Signatur-
Funktionen aus crypto/hybrid_kem.py.
"""

import pytest
from erebos_network.crypto.hybrid_kem import (
    sign_mail, verify_mail, verify_mail_with_status,
    VERIFIED, VERIFIED_OUTDATED, VERIFY_FAILED,
)


def test_sign_and_verify_roundtrip(fresh_keys_a):
    payload = b"hello world"
    sigs = sign_mail(
        ed25519_priv=bytes.fromhex(fresh_keys_a["ed25519_priv"]),
        mldsa_priv=bytes.fromhex(fresh_keys_a["mldsa_priv"]),
        payload=payload,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    assert len(sigs["ed25519"]) == 128
    assert len(sigs["mldsa"]) > 0
    assert sigs["mldsa_pub"] == fresh_keys_a["mldsa_pub"]

    ok = verify_mail(
        ed25519_pub=bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        payload=payload, signatures=sigs,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    assert ok is True


def test_verify_wrong_payload_fails(fresh_keys_a):
    sigs = sign_mail(
        ed25519_priv=bytes.fromhex(fresh_keys_a["ed25519_priv"]),
        mldsa_priv=bytes.fromhex(fresh_keys_a["mldsa_priv"]),
        payload=b"hello",
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    ok = verify_mail(
        ed25519_pub=bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        payload=b"bye", signatures=sigs,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    assert ok is False


def test_verify_wrong_pubkey_fails(fresh_keys_a, fresh_keys_b):
    sigs = sign_mail(
        ed25519_priv=bytes.fromhex(fresh_keys_a["ed25519_priv"]),
        mldsa_priv=bytes.fromhex(fresh_keys_a["mldsa_priv"]),
        payload=b"hello",
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    ok = verify_mail(
        ed25519_pub=bytes.fromhex(fresh_keys_b["ed25519_pub"]),
        payload=b"hello", signatures=sigs,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    assert ok is False


def test_verify_with_status_current_version(fresh_keys_a):
    sigs = sign_mail(
        ed25519_priv=bytes.fromhex(fresh_keys_a["ed25519_priv"]),
        mldsa_priv=bytes.fromhex(fresh_keys_a["mldsa_priv"]),
        payload=b"payload",
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    status = verify_mail_with_status(
        ed25519_pub=bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        payload=b"payload", signatures=sigs,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
        sender_key_version=1, sender_current_version=1,
    )
    assert status == VERIFIED


def test_verify_with_status_outdated(fresh_keys_a):
    sigs = sign_mail(
        ed25519_priv=bytes.fromhex(fresh_keys_a["ed25519_priv"]),
        mldsa_priv=bytes.fromhex(fresh_keys_a["mldsa_priv"]),
        payload=b"payload",
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    status = verify_mail_with_status(
        ed25519_pub=bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        payload=b"payload", signatures=sigs,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
        sender_key_version=1, sender_current_version=2,
    )
    assert status == VERIFIED_OUTDATED


def test_verify_with_status_future_version_fails(fresh_keys_a):
    sigs = sign_mail(
        ed25519_priv=bytes.fromhex(fresh_keys_a["ed25519_priv"]),
        mldsa_priv=bytes.fromhex(fresh_keys_a["mldsa_priv"]),
        payload=b"payload",
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    status = verify_mail_with_status(
        ed25519_pub=bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        payload=b"payload", signatures=sigs,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
        sender_key_version=2, sender_current_version=1,
    )
    assert status == VERIFY_FAILED


def test_verify_with_status_invalid_signature_fails(fresh_keys_a):
    status = verify_mail_with_status(
        ed25519_pub=bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        payload=b"payload",
        signatures={"ed25519": "00" * 64, "mldsa": "00" * 100},
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
        sender_key_version=1, sender_current_version=1,
    )
    assert status == VERIFY_FAILED
