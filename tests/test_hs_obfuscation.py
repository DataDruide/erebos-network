"""Tests fuer HS-Obfuskation."""

import pytest

from erebos_network.hs_obfuscation import (
    Burst,
    BurstBreaker,
    HSObfuscationConfig,
    HSObfuscator,
    ResponsePadding,
    SplashHS,
)


# --- BurstBreaker ---

def test_burst_breaker_init():
    """Burst-Breaker initialisiert."""
    b = BurstBreaker()
    assert b.stats["bursts_processed"] == 0


def test_burst_breaker_short():
    """Kurzer Burst bleibt unveraendert."""
    b = BurstBreaker()
    burst = Burst(packets=[100, 200], direction=1)
    result = b.break_burst(burst)
    assert len(result) == 1
    assert result[0].size == 2


def test_burst_breaker_long():
    """Langer Burst wird zerlegt (deterministisch, Jitter aus)."""
    config = HSObfuscationConfig(
        burst_threshold=3,
        burst_threshold_jitter=0.0,   # deterministisch
        padding_rate=0.0,
    )
    b = BurstBreaker(config)
    burst = Burst(packets=[100] * 9, direction=1)
    result = b.break_burst(burst)
    assert len(result) == 3  # 9 / 3 = 3 Bursts


def test_burst_breaker_long_adaptive():
    """Langer Burst mit Jitter: Chunk-Groesse variiert, aber begrenzt."""
    config = HSObfuscationConfig(
        burst_threshold=3,
        burst_threshold_jitter=0.3,
        padding_rate=0.0,
    )
    b = BurstBreaker(config)
    burst = Burst(packets=[100] * 30, direction=1)
    result = b.break_burst(burst)

    # Mindestens 2 Chunks, kein Chunk groesser als max Threshold
    assert len(result) >= 2
    max_threshold = int(
        config.burst_threshold * (1 + config.burst_threshold_jitter)
    )
    for chunk in result:
        assert chunk.size <= max_threshold, (
            f"Chunk zu gross: {chunk.size} > {max_threshold}"
        )


def test_burst_breaker_padding():
    """Burst-Breaker injiziert Padding."""
    config = HSObfuscationConfig(burst_threshold=3, padding_rate=1.0)
    b = BurstBreaker(config)
    burst = Burst(packets=[100] * 6, direction=1)
    result = b.break_burst(burst)
    # 2 echte Bursts + 2 Padding-Bursts (bei rate=1.0)
    assert b.stats["padding_injected"] > 0


def test_burst_breaker_stats():
    """Burst-Breaker-Statistiken."""
    b = BurstBreaker()
    burst = Burst(packets=[100] * 10, direction=1)
    b.break_burst(burst)
    stats = b.get_stats()
    assert stats["bursts_processed"] == 1


# --- SplashHS ---

def test_splash_init():
    """Splash initialisiert."""
    s = SplashHS()
    assert s.stats["splash_blocks"] == 0


def test_splash_injects():
    """Splash injiziert Bloecke."""
    config = HSObfuscationConfig(splash_blocks_min=2, splash_blocks_max=2)
    s = SplashHS(config)
    result = s.inject([100, 200, 300])
    assert len(result) == 5
    assert s.stats["splash_blocks"] == 2


def test_splash_disabled():
    """Splash deaktiviert."""
    config = HSObfuscationConfig(splash_enabled=False)
    s = SplashHS(config)
    result = s.inject([100, 200])
    assert result == [100, 200]


# --- ResponsePadding ---

def test_response_padding_init():
    """Response-Padding initialisiert."""
    r = ResponsePadding()
    assert r.stats["responses_padded"] == 0


def test_response_padding_pads():
    """Response wird gepolstert."""
    config = HSObfuscationConfig(response_padding_size=128)
    r = ResponsePadding(config)
    result = r.pad_response(b"hello")
    assert len(result) == 128


def test_response_padding_no_pad():
    """Response-Padding deaktiviert."""
    config = HSObfuscationConfig(response_padding_enabled=False)
    r = ResponsePadding(config)
    result = r.pad_response(b"hello")
    assert result == b"hello"


# --- HSObfuscator ---

def test_obfuscator_init():
    """Obfuscator initialisiert."""
    o = HSObfuscator()
    assert o.config.burst_threshold == 5


def test_obfuscator_trace():
    """Obfuscator verarbeitet Trace."""
    o = HSObfuscator()
    result = o.obfuscate_trace([100] * 20)
    assert len(result) > 0


def test_obfuscator_response():
    """Obfuscator verarbeitet Response."""
    o = HSObfuscator()
    result = o.obfuscate_response(b"Hello, HS!")
    assert len(result) >= len(b"Hello, HS!")


def test_obfuscator_stats():
    """Obfuscator-Statistiken."""
    o = HSObfuscator()
    o.obfuscate_trace([100] * 10)
    stats = o.get_stats()
    assert "burst_breaker" in stats
    assert "splash" in stats
    assert "response_padding" in stats


def test_obfuscator_custom_config():
    """Obfuscator mit Custom-Config."""
    config = HSObfuscationConfig(burst_threshold=10, padding_rate=0.5)
    o = HSObfuscator(config)
    assert o.config.burst_threshold == 10
    assert o.config.padding_rate == 0.5
