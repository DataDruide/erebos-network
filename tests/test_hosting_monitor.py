"""Tests für Hosting-Konzentrations-Monitoring (PeerDiscovery.as_distribution)."""

from erebos_network.discovery import DiscoveryConfig, PeerDiscovery


def _fresh_discovery() -> PeerDiscovery:
    return PeerDiscovery(
        own_address="127.0.0.1:1000",
        config=DiscoveryConfig(eclipse_protection=False, max_peers=100),
    )


class TestEmptyDiscovery:
    def test_empty_returns_zero_counts(self):
        d = _fresh_discovery()
        result = d.as_distribution()
        assert result["peer_count"] == 0
        assert result["unique_subnets"] == 0
        assert result["unparseable_addresses"] == 0
        assert result["top_subnets"] == []


class TestSubnetCounting:
    def test_single_peer_one_subnet(self):
        d = _fresh_discovery()
        d.add_peer("10.0.0.1:9000")
        result = d.as_distribution()
        assert result["peer_count"] == 1
        assert result["unique_subnets"] == 1
        assert result["top_subnets"][0]["count"] == 1
        assert result["top_subnets"][0]["share"] == 1.0

    def test_two_peers_same_subnet(self):
        d = _fresh_discovery()
        d.add_peer("10.0.0.1:9000")
        d.add_peer("10.0.0.2:9001")
        result = d.as_distribution()
        assert result["peer_count"] == 2
        assert result["unique_subnets"] == 1
        assert result["top_subnets"][0]["count"] == 2
        assert result["top_subnets"][0]["share"] == 1.0

    def test_two_peers_different_subnets(self):
        d = _fresh_discovery()
        d.add_peer("10.0.0.1:9000")
        d.add_peer("10.0.1.1:9001")
        result = d.as_distribution()
        assert result["peer_count"] == 2
        assert result["unique_subnets"] == 2

    def test_concentration_share(self):
        d = _fresh_discovery()
        for i in range(4):
            d.add_peer(f"192.168.1.{i+1}:9000")
        d.add_peer("10.0.0.1:9000")
        result = d.as_distribution()
        assert result["peer_count"] == 5
        assert result["top_subnets"][0]["count"] == 4
        assert result["top_subnets"][0]["share"] == 0.8


class TestUnparseable:
    def test_unparseable_addresses_counted(self):
        d = _fresh_discovery()
        d.add_peer("10.0.0.1:9000")
        from erebos_network.dht import PeerInfo
        d._known_peers["garbage"] = PeerInfo(
            peer_id="garbage",
            address="not-an-address",
        )
        result = d.as_distribution()
        assert result["unparseable_addresses"] >= 1
        assert result["peer_count"] == 1


class TestTopNLimit:
    def test_top_n_respected(self):
        d = _fresh_discovery()
        for i in range(10):
            d.add_peer(f"10.0.{i}.1:9000")
        result = d.as_distribution(top_n=3)
        assert result["unique_subnets"] == 10
        assert len(result["top_subnets"]) == 3


class TestIntegrationWithGetStats:
    def test_get_stats_includes_as_distribution(self):
        d = _fresh_discovery()
        d.add_peer("10.0.0.1:9000")
        stats = d.get_stats()
        assert "as_distribution" in stats
        assert stats["as_distribution"]["peer_count"] == 1
