"""Tests fuer CoverProfileDetector."""

from erebos_network.cover import CoverProfileDetector


class TestDetect:
    def test_too_few_frames_returns_web(self):
        d = CoverProfileDetector()
        for _ in range(5):
            d.notify_downlink(1000)
        assert d.detect() == "web"

    def test_small_frames_return_video(self):
        d = CoverProfileDetector()
        for _ in range(20):
            d.notify_downlink(1200)
        assert d.detect() == "video"

    def test_large_frames_return_api(self):
        d = CoverProfileDetector()
        for _ in range(20):
            d.notify_downlink(4000)
        assert d.detect() == "api"

    def test_medium_frames_return_web(self):
        d = CoverProfileDetector()
        for _ in range(20):
            d.notify_downlink(2500)
        assert d.detect() == "web"

    def test_window_size_limit(self):
        d = CoverProfileDetector(window_size=10)
        for _ in range(100):
            d.notify_downlink(1200)
        assert d.stats()["window_size"] == 10


class TestStats:
    def test_stats_structure(self):
        d = CoverProfileDetector()
        for _ in range(20):
            d.notify_downlink(1200)
        s = d.stats()
        assert "window_size" in s
        assert "median_size" in s
        assert "detected" in s
        assert s["detected"] == "video"
