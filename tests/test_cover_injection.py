"""Tests für TunnelCoverInjector und FRAME_COVER.

Nutzt einen Mock-Tunnel, der send_typed()-Aufrufe mitschreibt.
Kein echter Socket — reine Logik-Verifikation.
"""

import asyncio
import time

import pytest

from erebos_network.cover import CoverConfig, TunnelCoverInjector
from erebos_network.tunnel import FRAME_COVER, FRAME_DATA, FRAME_RELAY, FRAME_OPEN


class MockTunnel:
    """Zeichnet send_typed()-Aufrufe auf, ohne echten Socket."""

    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_typed(self, frame_type: int, payload: bytes) -> None:
        self.sent.append((frame_type, payload))

    async def close(self) -> None:
        self.closed = True


class TestFrameConstants:
    def test_frame_cover_distinct(self):
        assert FRAME_COVER == 0x04
        # Alle Frame-Types müssen unterschiedlich sein
        types = {FRAME_RELAY, FRAME_OPEN, FRAME_DATA, FRAME_COVER}
        assert len(types) == 4

    def test_frame_cover_not_collide_handshake(self):
        # Handshake-Codes sind 0x01/0x02, Frame-Types auch —
        # sie werden in verschiedenen Kontexten verwendet.
        assert FRAME_COVER != 0x00


class TestCoverConfigModes:
    def test_default_mode_is_poisson(self):
        cfg = CoverConfig()
        assert cfg.mode == "poisson"

    def test_burst_fields(self):
        cfg = CoverConfig(mode="burst", burst_size=3, burst_pause_seconds=0.5)
        assert cfg.burst_size == 3
        assert cfg.burst_pause_seconds == 0.5


@pytest.mark.asyncio
class TestTunnelCoverInjector:
    async def test_poisson_sends_frames(self):
        tunnel = MockTunnel()
        cfg = CoverConfig(mode="poisson", rate_per_second=100.0)
        inj = TunnelCoverInjector(tunnel, cfg)
        await inj.start()
        await asyncio.sleep(0.2)
        await inj.stop()
        assert inj.stats["frames_sent"] > 0
        assert all(ft == FRAME_COVER for ft, _ in tunnel.sent)

    async def test_constant_mode_interval(self):
        tunnel = MockTunnel()
        cfg = CoverConfig(mode="constant", rate_per_second=50.0)
        inj = TunnelCoverInjector(tunnel, cfg)
        await inj.start()
        await asyncio.sleep(0.15)
        await inj.stop()
        # Bei 50/s über 0.15s sollten ~7 Frames gesendet werden
        assert inj.stats["frames_sent"] >= 3

    async def test_burst_mode(self):
        tunnel = MockTunnel()
        cfg = CoverConfig(
            mode="burst",
            burst_size=3,
            burst_pause_seconds=0.05,
            rate_per_second=100.0,
        )
        inj = TunnelCoverInjector(tunnel, cfg)
        await inj.start()
        await asyncio.sleep(0.2)
        await inj.stop()
        # Mindestens ein Burst à 3 Frames
        assert inj.stats["frames_sent"] >= 3

    async def test_stop_is_idempotent(self):
        tunnel = MockTunnel()
        inj = TunnelCoverInjector(tunnel, CoverConfig())
        await inj.start()
        await inj.stop()
        await inj.stop()  # darf nicht crashen
        assert not inj.is_running

    async def test_stats_structure(self):
        tunnel = MockTunnel()
        inj = TunnelCoverInjector(tunnel, CoverConfig(mode="poisson"))
        stats = inj.get_stats()
        for key in ("frames_sent", "bytes_sent", "errors", "running",
                    "mode", "uptime_seconds", "rate_per_second"):
            assert key in stats

    async def test_send_error_does_not_crash(self):
        class FailingTunnel:
            async def send_typed(self, frame_type, payload):
                raise ConnectionError("simulated")

        tunnel = FailingTunnel()
        cfg = CoverConfig(mode="constant", rate_per_second=100.0)
        inj = TunnelCoverInjector(tunnel, cfg)
        await inj.start()
        await asyncio.sleep(0.1)
        await inj.stop()
        # Fehler gezählt, Loop beendet sich sauber
        assert inj.stats["errors"] >= 1
