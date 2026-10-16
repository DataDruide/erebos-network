"""Tests für adaptiven Cover-Traffic (P1.2)."""

import asyncio
import time

import pytest

from erebos_network.cover import CoverConfig, TunnelCoverInjector


class MockTunnel:
    def __init__(self):
        self.sent = []

    async def send_typed(self, frame_type, payload):
        self.sent.append((frame_type, payload))


class TestEffectiveRate:
    """Testet die Phasen-Logik ohne echten Loop."""

    def test_non_adaptive_returns_normal(self):
        cfg = CoverConfig(adaptive=False, rate_per_second=1.0)
        inj = TunnelCoverInjector(MockTunnel(), cfg)
        rate, phase = inj._effective_rate()
        assert phase == "normal"
        assert rate == 1.0

    def test_adaptive_no_traffic_yet_is_normal(self):
        cfg = CoverConfig(adaptive=True, rate_per_second=1.0)
        inj = TunnelCoverInjector(MockTunnel(), cfg)
        rate, phase = inj._effective_rate()
        assert phase == "normal"

    def test_adaptive_recent_traffic_is_quiet(self):
        cfg = CoverConfig(
            adaptive=True,
            rate_per_second=1.0,
            quiet_seconds_after_real=5.0,
            quiet_rate_factor=0.2,
        )
        inj = TunnelCoverInjector(MockTunnel(), cfg)
        inj.notify_real_traffic()
        rate, phase = inj._effective_rate()
        assert phase == "quiet"
        assert rate == pytest.approx(0.2)

    def test_adaptive_long_idle_is_boost(self):
        cfg = CoverConfig(
            adaptive=True,
            rate_per_second=1.0,
            quiet_seconds_after_real=1.0,
            boost_when_idle_seconds=1.0,
            boost_factor=2.0,
        )
        inj = TunnelCoverInjector(MockTunnel(), cfg)
        # Traffic vor 5 s
        inj._last_real_traffic_at = time.time() - 5.0
        rate, phase = inj._effective_rate()
        assert phase == "boost"
        assert rate == pytest.approx(2.0)

    def test_boost_factor_capped_at_2(self):
        cfg = CoverConfig(
            adaptive=True,
            rate_per_second=1.0,
            boost_when_idle_seconds=0.1,
            boost_factor=10.0,  # sollte auf 2.0 begrenzt werden
        )
        inj = TunnelCoverInjector(MockTunnel(), cfg)
        inj._last_real_traffic_at = time.time() - 5.0
        rate, phase = inj._effective_rate()
        assert rate == pytest.approx(2.0)

    def test_phase_between_quiet_and_boost(self):
        """Zwischen Quiet und Boost: normal."""
        cfg = CoverConfig(
            adaptive=True,
            rate_per_second=1.0,
            quiet_seconds_after_real=1.0,
            boost_when_idle_seconds=10.0,
        )
        inj = TunnelCoverInjector(MockTunnel(), cfg)
        inj._last_real_traffic_at = time.time() - 3.0
        rate, phase = inj._effective_rate()
        assert phase == "normal"
        assert rate == pytest.approx(1.0)


class TestNotifyRealTraffic:
    def test_notify_sets_timestamp(self):
        inj = TunnelCoverInjector(MockTunnel(), CoverConfig(adaptive=True))
        assert inj._last_real_traffic_at == 0.0
        inj.notify_real_traffic()
        assert inj._last_real_traffic_at > 0.0

    def test_notify_updates_timestamp(self):
        inj = TunnelCoverInjector(MockTunnel(), CoverConfig(adaptive=True))
        inj.notify_real_traffic()
        t1 = inj._last_real_traffic_at
        time.sleep(0.05)
        inj.notify_real_traffic()
        t2 = inj._last_real_traffic_at
        assert t2 > t1


class TestStatsIncludeAdaptive:
    def test_stats_have_adaptive_fields(self):
        cfg = CoverConfig(adaptive=True)
        inj = TunnelCoverInjector(MockTunnel(), cfg)
        stats = inj.get_stats()
        assert "adaptive" in stats
        assert "quiet_phases" in stats
        assert "boost_phases" in stats
        assert "seconds_since_real_traffic" in stats

    def test_stats_seconds_since_real_when_never(self):
        inj = TunnelCoverInjector(MockTunnel(), CoverConfig(adaptive=True))
        stats = inj.get_stats()
        assert stats["seconds_since_real_traffic"] is None

    def test_stats_seconds_since_real_after_notify(self):
        inj = TunnelCoverInjector(MockTunnel(), CoverConfig(adaptive=True))
        inj.notify_real_traffic()
        stats = inj.get_stats()
        assert stats["seconds_since_real_traffic"] is not None
        assert stats["seconds_since_real_traffic"] >= 0


@pytest.mark.asyncio
class TestAdaptiveLoop:
    async def test_quiet_phase_sends_fewer_frames(self):
        """Während Quiet-Phase sollten weniger Frames gesendet werden."""
        cfg = CoverConfig(
            adaptive=True,
            mode="constant",
            rate_per_second=100.0,
            quiet_seconds_after_real=10.0,
            quiet_rate_factor=0.1,  # 10/s statt 100/s
        )
        tunnel = MockTunnel()
        inj = TunnelCoverInjector(tunnel, cfg)
        inj.notify_real_traffic()  # → sofort quiet

        await inj.start()
        await asyncio.sleep(0.3)
        await inj.stop()

        # Bei 10/s über 0.3s: ~3 Frames (nicht 30)
        assert inj.stats["frames_sent"] < 10
        assert inj.stats["quiet_phases"] > 0

    async def test_boost_phase_sends_more_frames(self):
        """Während Boost-Phase sollten mehr Frames gesendet werden."""
        cfg = CoverConfig(
            adaptive=True,
            mode="constant",
            rate_per_second=20.0,
            quiet_seconds_after_real=0.1,
            boost_when_idle_seconds=0.1,
            boost_factor=2.0,
        )
        tunnel = MockTunnel()
        inj = TunnelCoverInjector(tunnel, cfg)
        # Traffic vor 5s → boost
        inj._last_real_traffic_at = time.time() - 5.0

        await inj.start()
        await asyncio.sleep(0.3)
        await inj.stop()

        # Bei 40/s über 0.3s: ~12 Frames
        assert inj.stats["frames_sent"] >= 6
        assert inj.stats["boost_phases"] > 0
