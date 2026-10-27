"""Tests fuer Timing-sichere Signatur-Verifikation.

Diese Tests pruefen NICHT die absolute Laufzeit (das waere flaky),
sondern stellen sicher, dass beide Signaturen IMMER geprueft werden,
auch wenn die erste fehlschlaegt.
"""

import pytest
from erebos_network.crypto.hybrid_kem import (
    sign_mail, verify_mail, _safe_ed25519_verify, _safe_mldsa_verify,
)


def test_safe_ed25519_verify_valid(fresh_keys_a):
    """_safe_ed25519_verify: gueltige Signatur -> True."""
    payload = b"test-payload"
    sigs = sign_mail(
        ed25519_priv=bytes.fromhex(fresh_keys_a["ed25519_priv"]),
        mldsa_priv=bytes.fromhex(fresh_keys_a["mldsa_priv"]),
        payload=payload,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    assert _safe_ed25519_verify(
        bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        sigs["ed25519"],
        payload,
    ) is True


def test_safe_ed25519_verify_invalid(fresh_keys_a):
    """_safe_ed25519_verify: ungueltige Signatur -> False (keine Exception)."""
    result = _safe_ed25519_verify(
        bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        "00" * 64,  # ungueltige Sig
        b"test-payload",
    )
    assert result is False


def test_safe_mldsa_verify_valid(fresh_keys_a):
    """_safe_mldsa_verify: gueltige Signatur -> True."""
    payload = b"test-payload"
    sigs = sign_mail(
        ed25519_priv=bytes.fromhex(fresh_keys_a["ed25519_priv"]),
        mldsa_priv=bytes.fromhex(fresh_keys_a["mldsa_priv"]),
        payload=payload,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )
    assert _safe_mldsa_verify(
        bytes.fromhex(fresh_keys_a["mldsa_pub"]),
        sigs["mldsa"],
        payload,
    ) is True


def test_safe_mldsa_verify_invalid(fresh_keys_a):
    """_safe_mldsa_verify: ungueltige Signatur -> False (keine Exception)."""
    result = _safe_mldsa_verify(
        bytes.fromhex(fresh_keys_a["mldsa_pub"]),
        "00" * 100,
        b"test-payload",
    )
    assert result is False


def test_safe_mldsa_verify_no_pubkey(fresh_keys_a):
    """_safe_mldsa_verify: ohne Pubkey -> False."""
    result = _safe_mldsa_verify(None, "00" * 100, b"test-payload")
    assert result is False


def test_verify_mail_checks_both(fresh_keys_a):
    """verify_mail: beide Signaturen werden geprueft.

    Wir koennen das nicht direkt an der Laufzeit messen (flaky),
    aber wir testen, dass ungueltige Ed25519 UND ungueltige ML-DSA
    BEIDE zu False fuehren — und dass eine gueltige Kombination True gibt.
    """
    payload = b"test-payload"
    sigs = sign_mail(
        ed25519_priv=bytes.fromhex(fresh_keys_a["ed25519_priv"]),
        mldsa_priv=bytes.fromhex(fresh_keys_a["mldsa_priv"]),
        payload=payload,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    )

    # Beide gueltig -> True
    assert verify_mail(
        ed25519_pub=bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        payload=payload,
        signatures=sigs,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    ) is True

    # Ed25519 ungueltig, ML-DSA gueltig -> False
    bad_ed = dict(sigs)
    bad_ed["ed25519"] = "00" * 64
    assert verify_mail(
        ed25519_pub=bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        payload=payload,
        signatures=bad_ed,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    ) is False

    # Ed25519 gueltig, ML-DSA ungueltig -> False
    bad_pq = dict(sigs)
    bad_pq["mldsa"] = "00" * 100
    assert verify_mail(
        ed25519_pub=bytes.fromhex(fresh_keys_a["ed25519_pub"]),
        payload=payload,
        signatures=bad_pq,
        mldsa_pub=bytes.fromhex(fresh_keys_a["mldsa_pub"]),
    ) is False
