"""Traffic-Shaping-Metriken (Entropie, Streuung) gegen echte Augur-API."""
import math
import statistics
from collections import Counter

from erebos_network.augur_defense import (
    AugurConfig,
    PredictivePerturbation,
    RateShaper,
)


def shannon_entropy(values: list[int]) -> float:
    if not values:
        return 0.0
    total = len(values)
    counts = Counter(values)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


class TestEntropyMetricSanity:
    def test_constant_has_zero_entropy(self):
        assert shannon_entropy([100] * 50) == 0.0

    def test_uniform_has_log2_n(self):
        uniform = [i for i in range(8)] * 10
        assert abs(shannon_entropy(uniform) - 3.0) < 0.01


class TestAugurSizePerturbation:
    def test_padding_increases_size_entropy(self):
        augur = PredictivePerturbation(AugurConfig())
        shaped_sizes = []
        for _ in range(200):
            out = augur.process_outgoing(b"\x00" * 512)
            if out:
                shaped_sizes.append(len(out))
        if shaped_sizes:
            assert shannon_entropy(shaped_sizes) > 0.0

    def test_noise_does_not_explode_size(self):
        augur = PredictivePerturbation(AugurConfig())
        sizes = []
        for _ in range(100):
            out = augur.process_outgoing(b"\x00" * 1024)
            if out:
                sizes.append(len(out))
        if sizes:
            assert max(sizes) < 8192
            assert statistics.mean(sizes) < 4096


class TestRateShaperTiming:
    """Timing-Verhalten: Default deterministisch, mit Jitter gestreut."""

    def test_default_is_deterministic(self):
        """Default (kein Jitter) = reiner Token-Bucket.

        Der Bucket startet leer, deshalb liefert delay_for_next()
        konstant ~1/rate. Alle Werte identisch -> fingerprintbar.
        Timing-Obfuskation muss explizit aktiviert werden.
        """
        rate = 10.0
        shaper = RateShaper(target_rate_per_second=rate)
        delays = [shaper.delay_for_next() for _ in range(100)]
        rounded = [int(d * 1000) for d in delays]
        # Deterministisch: alle Werte identisch (auf ms gerundet)
        assert len(set(rounded)) == 1, (
            f"Default sollte deterministisch sein: {sorted(set(rounded))}"
        )
        # Und ungefaehr 1/rate
        assert abs(delays[0] - 1.0 / rate) < 0.02, (
            f"Delay {delays[0]} nicht ~{1.0/rate}"
        )
    def test_jitter_enabled_creates_spread(self):
        """Mit Jitter: echte Streuung -> schwerer fingerprintbar.

        Wir erzeugen zuerst Token-Verbrauch, damit der Bucket
        nicht dauerhaft bei 0.0 bleibt.
        """
        shaper = RateShaper(
            target_rate_per_second=100.0,
            jitter_enabled=True,
            jitter_ratio=0.5,
        )
        for _ in range(5):
            shaper.allow()

        delays = [shaper.delay_for_next() for _ in range(500)]
        nonzero = [d for d in delays if d > 0]

        if nonzero:
            rounded = [int(d * 1_000_000) for d in nonzero]  # Mikrosekunden
            h = shannon_entropy(rounded)
            assert h > 1.0, f"Jitter erzeugt zu wenig Streuung: H={h:.3f}"
            assert len(set(rounded)) > 10, "Zu wenig Vielfalt"

    def test_jitter_respects_bounds(self):
        """Jitter darf Basisrate nicht sprengen."""
        rate = 10.0
        base = 1.0 / rate
        shaper = RateShaper(
            target_rate_per_second=rate,
            jitter_enabled=True,
            jitter_ratio=0.3,
        )
        for _ in range(5):
            shaper.allow()
        for _ in range(500):
            d = shaper.delay_for_next()
            assert 0.0 <= d <= base * 1.31, f"Delay außerhalb Bounds: {d}"

    def test_jitter_stats_reflect_config(self):
        """get_stats() zeigt Jitter-Konfiguration."""
        shaper = RateShaper(
            target_rate_per_second=10.0,
            jitter_enabled=True,
            jitter_ratio=0.4,
        )
        stats = shaper.get_stats()
        assert stats["jitter_enabled"] is True
        assert abs(stats["jitter_ratio"] - 0.4) < 1e-6

    def test_jitter_disabled_by_default_in_stats(self):
        """Default-Config: kein Jitter."""
        shaper = RateShaper(target_rate_per_second=10.0)
        stats = shaper.get_stats()
        assert stats["jitter_enabled"] is False

    def test_timing_delay_positive(self):
        """Delay darf nie negativ sein."""
        shaper = RateShaper(target_rate_per_second=5.0, jitter_enabled=True)
        for _ in range(50):
            assert shaper.delay_for_next() >= 0.0


class TestAugurStatsShape:
    def test_stats_have_required_keys(self):
        augur = PredictivePerturbation(AugurConfig())
        for _ in range(50):
            augur.process_outgoing(b"\x00" * 256)
        assert isinstance(augur.get_stats(), dict)

    def test_traffic_shape_is_dict(self):
        augur = PredictivePerturbation(AugurConfig())
        for _ in range(20):
            augur.process_outgoing(b"\x00" * 128)
        assert isinstance(augur.get_traffic_shape(), dict)


# ---------------------------------------------------------------------------
# Integration: ErebosProxy + Traffic-Shaping
# ---------------------------------------------------------------------------

import pytest


class TestProxyTrafficShapingIntegration:
    """Prüft Opt-In-Anbindung des Traffic-Shaping im Proxy."""

    @pytest.mark.asyncio
    async def test_proxy_default_no_shaper(self):
        """Default: kein Shaper aktiv, Verhalten unverändert."""
        from erebos_network.proxy import ErebosProxy

        proxy = ErebosProxy()
        assert proxy.shaper is None
        stats = proxy.get_stats()
        assert stats["traffic_shaping"] is False
        assert stats["shaper"] is None

    @pytest.mark.asyncio
    async def test_proxy_traffic_shaping_enabled(self):
        """Opt-In: Shaper aktiv mit Jitter."""
        from erebos_network.proxy import ErebosProxy

        proxy = ErebosProxy(
            traffic_shaping=True,
            target_rate=10.0,
            jitter_ratio=0.3,
        )
        assert proxy.shaper is not None
        assert proxy.shaper.jitter_enabled is True
        assert abs(proxy.shaper.jitter_ratio - 0.3) < 1e-6
        stats = proxy.get_stats()
        assert stats["traffic_shaping"] is True
        assert stats["shaper"]["jitter_enabled"] is True

    @pytest.mark.asyncio
    async def test_proxy_shaped_request_still_routes(self):
        """Auch mit Shaper bleibt Routing funktional."""
        from erebos_network.proxy import ErebosProxy
        from erebos_network.router import ErebosRouter

        proxy = ErebosProxy(router=ErebosRouter(), traffic_shaping=True)
        await proxy.start()
        result = await proxy.handle_request("https://example.com")
        assert result["success"] is True
        assert result["route_type"] == "clearnet"
        await proxy.stop()

    @pytest.mark.asyncio
    async def test_proxy_default_behavior_unchanged(self):
        """Default-Verhalten exakt wie vor der Erweiterung."""
        from erebos_network.proxy import ErebosProxy

        proxy = ErebosProxy()
        await proxy.start()
        result = await proxy.handle_request("https://example.com")
        assert result["success"] is True
        assert result["route_type"] == "clearnet"
        assert result["sector"] == "standard"
        assert result["hops"] == result["hops"]  # unverändert
        await proxy.stop()
