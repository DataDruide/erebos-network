"""Integrationstest für Traffic-Härtung im API-Server."""

import json
import time
import socket
import threading
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

from erebos_network.api import ErebosAPIHandler
from erebos_network.padding import pad_message
from erebos_network.delay import DelayConfig
from erebos_network.crypto.hybrid_kem import HybridKEM


@pytest.fixture
def live_server():
    """Startet API-Server auf freiem Port in Thread."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    server = HTTPServer(("127.0.0.1", port), ErebosAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)

    yield port

    server.shutdown()
    server.server_close()


def _get(port, path):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    headers = dict(resp.getheaders())
    body = resp.read()
    conn.close()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = None
    return resp.status, headers, data


class TestPaddingIntegration:
    def test_padding_header_present(self, live_server):
        status, headers, data = _get(live_server, "/status")
        assert status == 200
        assert "X-Erebos-Original-Size" in headers
        assert "X-Erebos-Padded-Size" in headers

    def test_padded_size_is_bucket_multiple(self, live_server):
        _, headers, _ = _get(live_server, "/api/community/governance")
        orig = int(headers["X-Erebos-Original-Size"])
        padded = int(headers["X-Erebos-Padded-Size"])
        assert padded >= orig
        assert padded % 256 == 0

    def test_body_is_valid_json_with_padding(self, live_server):
        _, _, data = _get(live_server, "/status")
        assert data is not None
        assert data.get("status") == "ok"


class TestTrafficStatsEndpoint:
    def test_traffic_stats_returns_all_sections(self, live_server):
        status, _, data = _get(live_server, "/api/network/traffic-stats")
        assert status == 200
        assert data["success"] is True
        for key in ("padding", "delay", "cover", "mixnet"):
            assert key in data["traffic"]

    def test_padding_section(self, live_server):
        _, _, data = _get(live_server, "/api/network/traffic-stats")
        assert data["traffic"]["padding"]["block_size"] == 256
        assert data["traffic"]["padding"]["active"] is True

    def test_delay_section(self, live_server):
        _, _, data = _get(live_server, "/api/network/traffic-stats")
        d = data["traffic"]["delay"]
        assert d["min_ms"] == 0
        assert d["max_ms"] == 30
        assert d["distribution"] == "uniform"


class TestPQCStatusEndpoint:
    def test_pqc_status(self, live_server):
        status, _, data = _get(live_server, "/api/network/pqc-status")
        assert status == 200
        assert data["success"] is True
        assert "ML-KEM" in data["pqc"]["algorithm"]
        assert data["pqc"]["nist_level"] >= 3

    def test_pqc_sizes_match_module(self, live_server):
        _, _, data = _get(live_server, "/api/network/pqc-status")
        expected = HybridKEM.sizes()
        assert data["pqc"]["algorithm"] == expected["algorithm"]


class TestPaddingUnit:
    def test_pad_message_bucket(self):
        padded = pad_message(b"x" * 100, block_size=256)
        assert padded.padded_size == 256

    def test_pad_message_exact_block(self):
        padded = pad_message(b"x" * 256, block_size=256)
        assert padded.padded_size == 512


class TestDelayConfig:
    def test_sample_within_bounds(self):
        cfg = DelayConfig(min_ms=0, max_ms=30, distribution="uniform")
        for _ in range(100):
            assert 0.0 <= cfg.sample() <= 0.030
