"""Tests für Delay."""

import pytest

from erebos_network.delay import (
    DELAY_CONFIGS,
    DelayConfig,
    apply_delay,
    get_delay_config,
)


def test_delay_config_sample():
    """Delay-Konfiguration gibt Werte zurück."""
    config = DelayConfig(min_ms=100, max_ms=200)
    for _ in range(10):
        delay = config.sample()
        assert 0.1 <= delay <= 0.2


def test_delay_config_zero():
    """Null-Delay funktioniert."""
    config = DelayConfig(min_ms=0, max_ms=0)
    assert config.sample() == 0.0


def test_delay_configs_exist():
    """Alle Konfigurationen existieren."""
    for name in ["none", "fast", "standard", "high", "mixnet"]:
        config = get_delay_config(name)
        assert config is not None


@pytest.mark.asyncio
async def test_apply_delay():
    """Delay wird angewendet."""
    config = DelayConfig(min_ms=10, max_ms=20)
    delay = await apply_delay(config)
    assert 0.01 <= delay <= 0.02


def test_exponential_distribution():
    """Exponentielle Verteilung funktioniert."""
    config = DelayConfig(min_ms=0, max_ms=1000, distribution="exponential")
    samples = [config.sample() for _ in range(100)]
    assert all(0 <= s <= 1.0 for s in samples)
