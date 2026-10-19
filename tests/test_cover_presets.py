"""Tests fuer CoverConfig.for_profile()."""

import pytest

from erebos_network.cover import CoverConfig


class TestForProfile:
    def test_web_profile(self):
        c = CoverConfig.for_profile("web")
        assert c.burst_size == 4
        assert c.burst_pause_seconds == 0.108
        assert c.max_size == 7008
        assert c.reactive_max_match == 86

    def test_video_profile(self):
        c = CoverConfig.for_profile("video")
        assert c.burst_size == 10
        assert c.burst_pause_seconds == 0.073
        assert c.max_size == 4048
        assert c.reactive_max_match == 207

    def test_api_profile(self):
        c = CoverConfig.for_profile("api")
        assert c.burst_size == 3
        assert c.burst_pause_seconds == 0.156
        assert c.max_size == 8609
        assert c.reactive_max_match == 20

    def test_unknown_profile_raises(self):
        with pytest.raises(ValueError, match="Unbekanntes Profil"):
            CoverConfig.for_profile("does-not-exist")

    def test_all_profiles_have_min_size(self):
        for name in ("web", "video", "api"):
            c = CoverConfig.for_profile(name)
            assert c.min_size >= 64
            assert c.inter_packet_ms >= 1

    def test_default_construction_still_works(self):
        c = CoverConfig()
        assert c.enabled is True
        assert c.mode == "poisson"  # Default unveraendert
