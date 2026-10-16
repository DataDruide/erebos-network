"""Tests für den Anonymitaets-Schwellenwert (small_set-Phase)."""

import time

from erebos_network.cover import CoverConfig, TunnelCoverInjector


class MockTunnel:
    def __init__(self):
        self.sent = []

    async def send_typed(self, frame_type, payload):
        self.sent.append((frame_type, payload))


class TestSmallSetPhase:
    def test_no_provider_is_small_set(self):
        inj = TunnelCoverInjector(
            MockTunnel(),
            CoverConfig(adaptive=True, rate_per_second=1.0, anonymity_threshold=10),
        )
        rate, phase = inj._effective_rate()
        assert phase == "small_set"
        assert rate == 2.0

    def test_provider_below_threshold_is_small_set(self):
        inj = TunnelCoverInjector(
            MockTunnel(),
            CoverConfig(adaptive=True, rate_per_second=1.0, anonymity_threshold=10),
            anonymity_provider=lambda: 5,
        )
        rate, phase = inj._effective_rate()
        assert phase == "small_set"
        assert rate == 2.0

    def test_provider_at_threshold_is_normal(self):
        inj = TunnelCoverInjector(
            MockTunnel(),
            CoverConfig(adaptive=True, rate_per_second=1.0, anonymity_threshold=10),
            anonymity_provider=lambda: 10,
        )
        rate, phase = inj._effective_rate()
        assert phase == "normal"
        assert rate == 1.0

    def test_provider_above_threshold_normal(self):
        inj = TunnelCoverInjector(
            MockTunnel(),
            CoverConfig(adaptive=True, rate_per_second=1.0, anonymity_threshold=10),
            anonymity_provider=lambda: 100,
        )
        _, phase = inj._effective_rate()
        assert phase == "normal"

    def test_provider_exception_falls_back_to_small_set(self):
        def bad_provider():
            raise RuntimeError("simulated failure")

        inj = TunnelCoverInjector(
            MockTunnel(),
            CoverConfig(adaptive=True, anonymity_threshold=10),
            anonymity_provider=bad_provider,
        )
        _, phase = inj._effective_rate()
        assert phase == "small_set"

    def test_small_set_dominates_over_quiet(self):
        inj = TunnelCoverInjector(
            MockTunnel(),
            CoverConfig(
                adaptive=True,
                rate_per_second=1.0,
                anonymity_threshold=10,
                quiet_seconds_after_real=10.0,
            ),
            anonymity_provider=lambda: 3,
        )
        inj.notify_real_traffic()
        _, phase = inj._effective_rate()
        assert phase == "small_set"

    def test_small_set_dominates_over_boost(self):
        inj = TunnelCoverInjector(
            MockTunnel(),
            CoverConfig(
                adaptive=True,
                rate_per_second=1.0,
                anonymity_threshold=10,
                boost_when_idle_seconds=0.1,
            ),
            anonymity_provider=lambda: 3,
        )
        inj._last_real_traffic_at = time.time() - 100.0
        _, phase = inj._effective_rate()
        assert phase == "small_set"

    def test_non_adaptive_ignores_small_set(self):
        inj = TunnelCoverInjector(
            MockTunnel(),
            CoverConfig(adaptive=False, anonymity_threshold=10),
            anonymity_provider=lambda: 1,
        )
        _, phase = inj._effective_rate()
        assert phase == "normal"


class TestAnonymityStats:
    def test_get_stats_includes_anonymity_fields(self):
        inj = TunnelCoverInjector(
            MockTunnel(),
            CoverConfig(adaptive=True, anonymity_threshold=10),
            anonymity_provider=lambda: 42,
        )
        stats = inj.get_stats()
        assert "anonymity_set_size" in stats
        assert "anonymity_threshold" in stats
        assert "small_set_phases" in stats
        assert stats["anonymity_set_size"] == 42
        assert stats["anonymity_threshold"] == 10

    def test_stats_without_provider_shows_zero(self):
        inj = TunnelCoverInjector(
            MockTunnel(),
            CoverConfig(adaptive=True),
        )
        stats = inj.get_stats()
        assert stats["anonymity_set_size"] == 0
