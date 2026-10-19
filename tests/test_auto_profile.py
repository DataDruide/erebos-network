"""Tests fuer Auto-Profil-Erkennung im TunnelCoverInjector."""

import asyncio
import pytest

from erebos_network.cover import (
    CoverConfig,
    CoverProfileDetector,
    TunnelCoverInjector,
)


class MockTunnel:
    def __init__(self):
        self.sent = []

    async def send_typed(self, frame_type, payload):
        self.sent.append((frame_type, payload))


@pytest.mark.asyncio
async def test_auto_profile_switches_config():
    """Wenn der Detector 'video' erkennt, wechselt die Config."""
    tunnel = MockTunnel()
    cfg = CoverConfig.for_profile("web")
    inj = TunnelCoverInjector(
        tunnel,
        cfg,
        anonymity_provider=lambda: 100,
        auto_profile=True,
    )
    inj._current_profile = "web"

    # Detector mit kleinen Frames fuellen (video)
    for _ in range(20):
        inj.notify_downlink(1200)

    # Kurz laufen lassen
    await inj.start()
    await asyncio.sleep(0.3)
    await inj.stop()

    # Config sollte auf video gewechselt sein
    assert inj._current_profile == "video"
    assert cfg.burst_size == 10
    assert cfg.max_size == 4048


@pytest.mark.asyncio
async def test_auto_profile_disabled_keeps_config():
    """Ohne auto_profile bleibt die Config unveraendert."""
    tunnel = MockTunnel()
    cfg = CoverConfig.for_profile("web")
    original_burst = cfg.burst_size
    inj = TunnelCoverInjector(
        tunnel,
        cfg,
        anonymity_provider=lambda: 100,
        auto_profile=False,
    )

    for _ in range(20):
        inj.notify_downlink(1200)

    await inj.start()
    await asyncio.sleep(0.3)
    await inj.stop()

    assert cfg.burst_size == original_burst


def test_stats_include_auto_profile():
    """Stats enthalten auto_profile-Felder."""
    inj = TunnelCoverInjector(
        MockTunnel(),
        CoverConfig(),
        auto_profile=True,
    )
    stats = inj.get_stats()
    assert "auto_profile" in stats
    assert "auto_profile_current" in stats
    assert "auto_profile_changes" in stats
