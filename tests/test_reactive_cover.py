"""Tests für reactive Drop-Cover (P1.3, Nym-Lehre)."""

import asyncio
import time

import pytest

from erebos_network.cover import CoverConfig, TunnelCoverInjector
from erebos_network.tunnel import FRAME_COVER


class MockTunnel:
    def __init__(self):
        self.sent = []

    async def send_typed(self, frame_type, payload):
        self.sent.append((frame_type, payload))


def _mk_injector(**cfg_kwargs):
    defaults = dict(
        adaptive=True,
        reactive=True,
        reactive_window_ms=100,
        reactive_max_match=10,
        reactive_size_jitter=0.3,
        mode="poisson",
        rate_per_second=0.1,
        anonymity_threshold=10,
    )
    defaults.update(cfg_kwargs)
    tunnel = MockTunnel()
    inj = TunnelCoverInjector(
        tunnel,
        CoverConfig(**defaults),
        anonymity_provider=lambda: 100,
    )
    return tunnel, inj


class TestDownlinkTracking:
    def test_notify_downlink_appends_event(self):
        _, inj = _mk_injector()
        inj.notify_downlink(500)
        assert len(inj._downlink_events) == 1
        ts, size = inj._downlink_events[0]
        assert size == 500
        assert ts > 0

    def test_negative_size_clamped_to_zero(self):
        _, inj = _mk_injector()
        inj.notify_downlink(-100)
        _, size = inj._downlink_events[0]
        assert size == 0

    def test_trim_downlink_window_removes_old(self):
        _, inj = _mk_injector(reactive_window_ms=50)
        inj._downlink_events.append((time.time() - 1.0, 500))
        inj.notify_downlink(600)
        inj._trim_downlink_window(time.time())
        assert len(inj._downlink_events) == 1
        _, size = inj._downlink_events[0]
        assert size == 600

    def test_burst_stats_empty(self):
        _, inj = _mk_injector()
        count, avg = inj._downlink_burst_stats()
        assert count == 0
        assert avg == 0

    def test_burst_stats_counts(self):
        _, inj = _mk_injector()
        inj.notify_downlink(400)
        inj.notify_downlink(600)
        inj.notify_downlink(500)
        count, avg = inj._downlink_burst_stats()
        assert count == 3
        assert avg == 500


@pytest.mark.asyncio
class TestReactiveBurst:
    async def test_send_reactive_burst_sends_frames(self):
        tunnel, inj = _mk_injector()
        inj.notify_downlink(500)
        inj.notify_downlink(600)
        await inj._send_reactive_burst()
        assert len(tunnel.sent) == 2
        assert all(ft == FRAME_COVER for ft, _ in tunnel.sent)

    async def test_send_reactive_burst_clears_events(self):
        _, inj = _mk_injector()
        inj.notify_downlink(500)
        await inj._send_reactive_burst()
        assert len(inj._downlink_events) == 0

    async def test_reactive_max_match_limits(self):
        tunnel, inj = _mk_injector(reactive_max_match=3)
        for _ in range(10):
            inj.notify_downlink(500)
        await inj._send_reactive_burst()
        assert len(tunnel.sent) == 3

    async def test_size_within_jitter(self):
        tunnel, inj = _mk_injector(reactive_size_jitter=0.3)
        for _ in range(5):
            inj.notify_downlink(1000)
        await inj._send_reactive_burst()
        for _, payload in tunnel.sent:
            assert 700 <= len(payload) <= 1300

    async def test_stats_counters_increment(self):
        tunnel, inj = _mk_injector()
        for _ in range(4):
            inj.notify_downlink(500)
        await inj._send_reactive_burst()
        assert inj.stats["reactive_frames"] == 4
        assert inj.stats["reactive_bursts"] == 1
        assert inj.stats["frames_sent"] >= 4


@pytest.mark.asyncio
class TestReactiveLoop:
    async def test_loop_triggers_on_downlink(self):
        tunnel, inj = _mk_injector(rate_per_second=0.01, burst_size=1)
        inj.notify_downlink(500)
        await inj.start()
        await asyncio.sleep(0.3)
        await inj.stop()
        assert inj.stats["reactive_frames"] >= 1

    async def test_loop_ignores_downlink_when_disabled(self):
        tunnel, inj = _mk_injector(
            reactive=False,
            rate_per_second=0.01,
        )
        inj.notify_downlink(500)
        await inj.start()
        await asyncio.sleep(0.3)
        await inj.stop()
        assert inj.stats["reactive_frames"] == 0
