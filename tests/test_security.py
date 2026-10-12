"""Tests fuer Hybrid-KEM, Poisson-Delay und konstanten Cover-Traffic."""

import asyncio

import pytest

from erebos_network.crypto.hybrid_kem import HybridKEM, HybridKeyPair
from erebos_network.delay import (
    DelayConfig,
    apply_delay,
    poisson_inter_arrival,
)
from erebos_network.cover import ConstantCoverTraffic, CoverConfig


# --- Hybrid-KEM Tests ---

def test_hybrid_kem_sizes():
    """Hybrid-KEM Groessen stimmen."""
    sizes = HybridKEM.sizes()
    assert sizes["algorithm"] == "X25519+ML-KEM-1024"
    assert sizes["x25519_public"] == 32
    assert sizes["mlkem_public"] == 1568
    assert sizes["shared_secret"] == 32
    assert sizes["nist_level"] == 5


def test_hybrid_kem_generate():
    """Hybrid KeyPair wird generiert."""
    kem = HybridKEM()
    kp = kem.generate_keypair()
    assert isinstance(kp, HybridKeyPair)
    assert len(kp.x25519_public) == 32
    assert len(kp.mlkem_public) == 1568


def test_hybrid_kem_encapsulate_decapsulate():
    """Encapsulate + Decapsulate ergeben dasselbe Secret."""
    kem = HybridKEM()
    kp = kem.generate_keypair()
    ciphertext, secret1 = kem.encapsulate(kp)
    secret2 = kem.decapsulate(ciphertext, kp)
    assert secret1 == secret2
    assert len(secret1) == 32


def test_hybrid_kem_different_secrets():
    """Unterschiedliche Encapsulations ergeben unterschiedliche Secrets."""
    kem = HybridKEM()
    kp = kem.generate_keypair()
    _, s1 = kem.encapsulate(kp)
    _, s2 = kem.encapsulate(kp)
    assert s1 != s2


# --- Poisson-Delay Tests ---

def test_poisson_inter_arrival():
    """Poisson-Inter-Arrival gibt Werte zurueck."""
    for _ in range(10):
        t = poisson_inter_arrival(1.0)
        assert t > 0


def test_poisson_distribution():
    """Poisson-Verteilung in DELAY_CONFIGS."""
    from erebos_network.delay import DELAY_CONFIGS
    mixnet = DELAY_CONFIGS["mixnet"]
    assert mixnet.distribution == "poisson"


def test_delay_poisson_sample():
    """Poisson-Sample funktioniert."""
    config = DelayConfig(min_ms=0, max_ms=1000, distribution="poisson")
    samples = [config.sample() for _ in range(50)]
    assert all(0 <= s <= 1.0 for s in samples)
    # Poisson sollte viele kleine Werte haben
    small = sum(1 for s in samples if s < 0.5)
    assert small > 20


@pytest.mark.asyncio
async def test_apply_delay_poisson():
    """Apply Delay mit Poisson funktioniert."""
    config = DelayConfig(min_ms=10, max_ms=100, distribution="poisson")
    delay = await apply_delay(config)
    assert 0 < delay <= 0.1


# --- Constant Cover Traffic Tests ---

@pytest.mark.asyncio
async def test_constant_cover_start_stop():
    """Konstanter Cover-Traffic startet und stoppt."""
    config = CoverConfig(enabled=True, rate_per_second=10.0)
    ct = ConstantCoverTraffic(config)
    assert ct.is_running is False
    await ct.start()
    assert ct.is_running is True
    await ct.stop()
    assert ct.is_running is False


@pytest.mark.asyncio
async def test_constant_cover_sends():
    """Konstanter Cover-Traffic sendet Nachrichten."""
    config = CoverConfig(enabled=True, rate_per_second=50.0)
    ct = ConstantCoverTraffic(config)
    await ct.start()
    await asyncio.sleep(0.3)
    await ct.stop()
    stats = ct.get_stats()
    assert stats["messages_sent"] > 0
    assert stats["bytes_sent"] > 0


@pytest.mark.asyncio
async def test_constant_cover_rate():
    """Konstanter Cover-Traffic haelt ungefaehr die Rate."""
    config = CoverConfig(enabled=True, rate_per_second=20.0)
    ct = ConstantCoverTraffic(config)
    await ct.start()
    await asyncio.sleep(1.0)
    await ct.stop()
    stats = ct.get_stats()
    # 20/s * 1s = ~20, mit Toleranz
    assert 5 <= stats["messages_sent"] <= 50
