"""Tests fuer HS-Descriptor-Hardening."""

import time

import pytest

from erebos_network.hs_hardening import (
    HSDescriptorHardening,
    HSHardeningConfig,
)


# --- Hardening Unit Tests ---

def test_hardening_compute_pow():
    """PoW wird berechnet."""
    h = HSDescriptorHardening()
    pow_hash, nonce = h.compute_pow("svc1", "desc1", difficulty=2)
    assert pow_hash.startswith("00")
    assert nonce >= 0


def test_hardening_verify_pow():
    """PoW wird verifiziert."""
    h = HSDescriptorHardening()
    pow_hash, nonce = h.compute_pow("svc1", "desc1", difficulty=2)
    assert h.verify_pow("svc1", "desc1", nonce, 2, pow_hash) is True


def test_hardening_verify_pow_wrong():
    """Falscher PoW wird abgelehnt."""
    h = HSDescriptorHardening()
    pow_hash, nonce = h.compute_pow("svc1", "desc1", difficulty=2)
    assert h.verify_pow("svc2", "desc1", nonce, 2, pow_hash) is False


def test_hardening_accepts_valid():
    """Gueltiger Descriptor wird akzeptiert."""
    h = HSDescriptorHardening()
    pow_hash, nonce = h.compute_pow("svc1", "desc1", difficulty=2)
    h.config.pow_difficulty = 2
    assert h.publish("svc1", "desc1", b"data", pow_hash, nonce) is True


def test_hardening_rejects_oversized():
    """Zu grosser Descriptor wird abgelehnt."""
    h = HSDescriptorHardening()
    h.config.pow_difficulty = 2
    big_data = b"x" * (h.config.max_descriptor_size + 1)
    pow_hash, nonce = h.compute_pow("svc1", "desc1", difficulty=2)
    assert h.publish("svc1", "desc1", big_data, pow_hash, nonce) is False
    assert h.stats["rejected_size"] == 1


def test_hardening_rejects_per_service():
    """Pro-Service-Limit wird durchgesetzt."""
    h = HSDescriptorHardening()
    h.config.pow_difficulty = 2
    h.config.max_descriptors_per_service = 3

    for i in range(3):
        did = f"desc{i}"
        ph, pn = h.compute_pow("svc1", did, difficulty=2)
        assert h.publish("svc1", did, b"data", ph, pn) is True

    did = "desc4"
    ph, pn = h.compute_pow("svc1", did, difficulty=2)
    assert h.publish("svc1", did, b"data", ph, pn) is False
    assert h.stats["rejected_per_service"] == 1


def test_hardening_rejects_rate_limit():
    """Rate-Limit wird durchgesetzt."""
    h = HSDescriptorHardening()
    h.config.pow_difficulty = 2
    h.config.rate_limit_per_minute = 2

    for i in range(2):
        did = f"desc{i}"
        ph, pn = h.compute_pow("svc1", did, difficulty=2)
        h.publish("svc1", did, b"data", ph, pn)

    did = "desc3"
    ph, pn = h.compute_pow("svc1", did, difficulty=2)
    assert h.publish("svc1", did, b"data", ph, pn) is False
    assert h.stats["rejected_rate_limit"] >= 1


def test_hardening_cleanup():
    """Cleanup entfernt abgelaufene Descriptors."""
    h = HSDescriptorHardening()
    h.config.pow_difficulty = 2
    h.config.descriptor_ttl_seconds = 0

    ph, pn = h.compute_pow("svc1", "desc1", difficulty=2)
    h.publish("svc1", "desc1", b"data", ph, pn)

    removed = h.cleanup(force=True)
    assert removed == 1


def test_hardening_stats():
    """Statistiken funktionieren."""
    h = HSDescriptorHardening()
    h.config.pow_difficulty = 2
    ph, pn = h.compute_pow("svc1", "desc1", difficulty=2)
    h.publish("svc1", "desc1", b"data", ph, pn)
    stats = h.get_stats()
    assert stats["descriptors_accepted"] == 1


# --- Integration Tests ---



