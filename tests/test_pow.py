"""Tests für Proof-of-Work."""

import pytest

from erebos_network.pow import (
    PoWConfig,
    compute_pow,
    estimate_pow_time,
    verify_pow,
)


def test_compute_pow_basic():
    """PoW wird berechnet."""
    result = compute_pow("test-address", difficulty=2)
    assert result.peer_id.startswith("00")
    assert result.difficulty == 2
    assert result.nonce >= 0


def test_verify_pow():
    """PoW wird verifiziert."""
    result = compute_pow("test-address", difficulty=2)
    assert verify_pow(
        result.peer_id,
        "test-address",
        result.nonce,
        2,
    ) is True


def test_verify_pow_wrong_difficulty():
    """PoW mit falscher Difficulty schlägt fehl."""
    result = compute_pow("test-address", difficulty=2)
    assert verify_pow(
        result.peer_id,
        "test-address",
        result.nonce,
        5,
    ) is False


def test_verify_pow_wrong_seed():
    """PoW mit falschem Seed schlägt fehl."""
    result = compute_pow("test-address", difficulty=2)
    assert verify_pow(
        result.peer_id,
        "wrong-address",
        result.nonce,
        2,
    ) is False


def test_pow_config():
    """PoW-Config funktioniert."""
    config = PoWConfig(difficulty=3)
    assert config.difficulty == 3


def test_estimate_pow_time():
    """PoW-Zeit wird geschätzt."""
    t1 = estimate_pow_time(1)
    t2 = estimate_pow_time(4)
    assert t2 > t1
    assert t1 > 0
