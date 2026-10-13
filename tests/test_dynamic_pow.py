"""Tests fuer Dynamic PoW."""

import time

import pytest

from erebos_network.dynamic_pow import (
    DynamicPoW,
    DynamicPoWConfig,
    IPRateLimiter,
    PeerAttempt,
)


# --- IPRateLimiter ---

def test_rate_limiter_init():
    """Rate-Limiter initialisiert."""
    rl = IPRateLimiter()
    assert rl.stats["attempts_total"] == 0


def test_rate_limiter_extract_ip():
    """IP wird extrahiert."""
    rl = IPRateLimiter()
    assert rl._extract_ip("192.168.1.1:8000") == "192.168.1.1"
    assert rl._extract_ip("[::1]:8000") == "::1"


def test_rate_limiter_extract_subnet():
    """Subnetz wird extrahiert."""
    rl = IPRateLimiter()
    assert rl._extract_subnet("192.168.1.100") == "192.168.1.0/24"


def test_rate_limiter_allows():
    """Rate-Limiter erlaubt erste Versuche."""
    rl = IPRateLimiter()
    assert rl.allow("192.168.1.1:8000") is True


def test_rate_limiter_rejects_many_from_same_ip():
    """Rate-Limiter lehnt zu viele von derselben IP ab."""
    config = DynamicPoWConfig(max_new_peers_per_ip_per_hour=3)
    rl = IPRateLimiter(config)
    for i in range(3):
        rl.allow(f"192.168.1.1:{8000+i}")
    assert rl.allow("192.168.1.1:9000") is False
    assert rl.stats["rejected_ip"] == 1


def test_rate_limiter_rejects_many_from_subnet():
    """Rate-Limiter lehnt zu viele aus demselben Subnetz ab."""
    config = DynamicPoWConfig(
        max_new_peers_per_ip_per_hour=100,
        max_new_peers_per_subnet_per_hour=5,
    )
    rl = IPRateLimiter(config)
    for i in range(5):
        rl.allow(f"192.168.1.{i+1}:8000")
    assert rl.allow("192.168.1.100:8000") is False


# --- DynamicPoW ---

def test_pow_init():
    """DynamicPoW initialisiert."""
    p = DynamicPoW()
    assert p.current_difficulty == 3


def test_pow_compute():
    """PoW wird berechnet."""
    h, nonce = DynamicPoW.compute_pow("test-seed", difficulty=2)
    assert h.startswith("00")
    assert nonce >= 0


def test_pow_verify():
    """PoW wird verifiziert."""
    h, nonce = DynamicPoW.compute_pow("test-seed", difficulty=2)
    assert DynamicPoW.verify_pow("test-seed", nonce, 2, h) is True


def test_pow_verify_wrong_seed():
    """Falscher Seed schlaegt fehl."""
    h, nonce = DynamicPoW.compute_pow("test-seed", difficulty=2)
    assert DynamicPoW.verify_pow("wrong-seed", nonce, 2, h) is False


def test_difficulty_base():
    """Basis-Difficulty."""
    p = DynamicPoW()
    diff = p.compute_difficulty()
    assert diff == 3


def test_difficulty_scales_with_peers():
    """Difficulty skaliert mit Netzwerkgroesse."""
    p = DynamicPoW()
    p.update_peer_count(10000)
    diff = p.compute_difficulty()
    assert diff > 3


def test_difficulty_reputation_bypass():
    """Reputation senkt Difficulty."""
    p = DynamicPoW()
    diff_low = p.compute_difficulty(reputation=0.5)
    p._current_difficulty = 5  # reset
    diff_high = p.compute_difficulty(reputation=0.9)
    # Hohe Reputation sollte niedrigere Difficulty haben
    assert diff_high <= diff_low


def test_difficulty_bounds():
    """Difficulty bleibt in Grenzen."""
    p = DynamicPoW()
    p.update_peer_count(1000000)
    diff = p.compute_difficulty()
    assert diff <= p.config.max_difficulty
    assert diff >= p.config.min_difficulty


def test_register_peer():
    """Peer wird registriert."""
    p = DynamicPoW()
    result = p.register_peer("192.168.1.1:8000")
    assert result["status"] == "accepted"
    assert "nonce" in result
    assert "pow_hash" in result


def test_register_peer_rate_limit():
    """Rate-Limit blockiert Registrierung."""
    config = DynamicPoWConfig(max_new_peers_per_ip_per_hour=1)
    p = DynamicPoW(config)
    p.register_peer("192.168.1.1:8000")
    result = p.register_peer("192.168.1.1:8001")
    assert result["status"] == "rejected"
    assert result["reason"] == "rate_limit"


def test_verify_peer():
    """Peer wird verifiziert."""
    p = DynamicPoW()
    result = p.register_peer("192.168.1.1:8000")
    verified = p.verify_peer(
        "192.168.1.1:8000",
        result["seed"],
        result["nonce"],
        result["pow_hash"],
        result["difficulty"],
    )
    assert verified is True


def test_attack_detection():
    """Angriff wird erkannt."""
    config = DynamicPoWConfig(attack_threshold_per_minute=5)
    p = DynamicPoW(config)
    # Simuliere viele Versuche
    for i in range(10):
        p.register_peer(f"10.0.0.{i}:8000")
    # Nach 10 Versuchen sollte der Angriff erkannt sein
    assert p.stats["attacks_detected"] >= 1


def test_attack_increases_difficulty():
    """Angriff erhoeht Difficulty."""
    config = DynamicPoWConfig(attack_threshold_per_minute=5)
    p = DynamicPoW(config)
    initial = p.compute_difficulty()
    for i in range(10):
        p.register_peer(f"10.0.0.{i}:8000")
    after = p.compute_difficulty()
    assert after >= initial


def test_pow_stats():
    """PoW-Statistiken."""
    p = DynamicPoW()
    p.register_peer("192.168.1.1:8000")
    stats = p.get_stats()
    assert stats["pow_computed"] >= 1
    assert "rate_limiter" in stats
