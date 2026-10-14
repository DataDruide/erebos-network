"""Tests für den Erebos-Proxy."""

import pytest

from erebos_network.proxy import ErebosProxy
from erebos_network.sectors import SectorType


@pytest.mark.asyncio
async def test_proxy_start_stop():
    """Proxy startet und stoppt."""
    proxy = ErebosProxy()
    await proxy.start()
    stats = proxy.get_stats()
    assert stats["running"] is True

    await proxy.stop()
    stats = proxy.get_stats()
    assert stats["running"] is False


@pytest.mark.asyncio
async def test_proxy_handle_clearnet():
    """Proxy behandelt Clearnet-Anfragen."""
    proxy = ErebosProxy()
    await proxy.start()

    result = await proxy.handle_request("https://example.com")
    assert result["success"] is True
    assert result["route_type"] == "clearnet"
    assert result["sector"] == "standard"

    await proxy.stop()


@pytest.mark.asyncio
async def test_proxy_handle_i2p():
    """Proxy behandelt I2P-Anfragen."""
    proxy = ErebosProxy()
    await proxy.start()

    result = await proxy.handle_request("http://stats.i2p")
    assert result["success"] is True
    assert result["route_type"] == "eepsite"

    await proxy.stop()


@pytest.mark.asyncio
async def test_proxy_sector_override():
    """Proxy respektiert Sektor-Override."""
    proxy = ErebosProxy()
    await proxy.start()

    result = await proxy.handle_request("https://example.com", SectorType.MIXNET)
    assert result["success"] is True
    assert result["sector"] == "mixnet"
    assert result["hops"] == 7

    await proxy.stop()


@pytest.mark.asyncio
async def test_proxy_stats():
    """Proxy-Statistiken werden gezählt."""
    proxy = ErebosProxy()
    await proxy.start()

    await proxy.handle_request("https://example.com")
    await proxy.handle_request("http://stats.i2p")
    await proxy.handle_request("http://my-service.erebos")

    stats = proxy.get_stats()
    assert stats["requests_total"] == 3
    assert stats["requests_routed"] == 3

    await proxy.stop()


# ---------------------------------------------------------------------------
# SOCKS5-Config (Refactor-Tests)
# ---------------------------------------------------------------------------

from pathlib import Path
from erebos_network.proxy import ErebosSocks5Server, Socks5Config


def test_socks5_config_defaults():
    """Default-Config hat die historischen Werte."""
    cfg = Socks5Config()
    assert cfg.entry_host == "127.0.0.1"
    assert cfg.entry_port == 9999
    assert cfg.relay1_port == 9998
    assert cfg.relay2_port == 9997
    assert cfg.peer1_name == "peer1"
    assert cfg.peer2_name == "peer2"
    assert cfg.peer3_name == "peer3"
    assert cfg.connect_timeout == 10.0


def test_socks5_config_peer_pub_path():
    """peer_pub_path() liefert den korrekten Dateinamen."""
    cfg = Socks5Config(keys_dir=Path("/custom/keys"))
    assert cfg.peer_pub_path("peer1") == Path("/custom/keys/peer1_x25519.pub")
    assert cfg.peer_pub_path("alice") == Path("/custom/keys/alice_x25519.pub")


def test_socks5_config_custom_keys_dir():
    """Custom keys_dir wird respektiert."""
    cfg = Socks5Config(keys_dir=Path("/tmp/keys"))
    assert cfg.keys_dir == Path("/tmp/keys")


def test_socks5_server_uses_default_config():
    """ErebosSocks5Server ohne config nutzt Default-Werte."""
    proxy = ErebosProxy()
    server = ErebosSocks5Server(proxy, port=5555)
    assert server.config is not None
    assert server.config.entry_port == 9999
    assert server.port == 5555


def test_socks5_server_loads_keys_from_config(tmp_path):
    """Server lädt Keys aus konfiguriertem Verzeichnis."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    # 3 Test-Keypairs im tmp_path erzeugen
    for name in ("peer1", "peer2", "peer3"):
        priv = X25519PrivateKey.generate()
        pub = priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        (tmp_path / f"{name}_x25519.pub").write_bytes(pub)

    proxy = ErebosProxy()
    server = ErebosSocks5Server(
        proxy,
        config=Socks5Config(keys_dir=tmp_path),
    )
    assert len(server.peer1_pub) == 32
    assert len(server.peer2_pub) == 32
    assert len(server.peer3_pub) == 32


def test_socks5_server_custom_ports():
    """Custom Ports werden respektiert."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in ("a", "b", "c"):
            priv = X25519PrivateKey.generate()
            pub = priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            (tmp / f"{name}_x25519.pub").write_bytes(pub)

        cfg = Socks5Config(
            keys_dir=tmp,
            peer_pool=["a", "b", "c"],
            entry_port=7777, relay1_port=7778, relay2_port=7779,
        )
        server = ErebosSocks5Server(ErebosProxy(), config=cfg)
        assert server.peer1_port == 7777
        assert server.peer2_port == 7778
        assert server.peer3_port == 7779


# ---------------------------------------------------------------------------
# Byte-Stream Timing-Hardening
# ---------------------------------------------------------------------------

import asyncio
from erebos_network.augur_defense import RateShaper


def test_socks5_config_traffic_shaping_default_off():
    """Default: traffic_shaping ist aus (Backward-Compat)."""
    cfg = Socks5Config()
    assert cfg.traffic_shaping is False
    assert cfg.target_rate == 10.0
    assert cfg.jitter_ratio == 0.3


def test_socks5_server_no_shaper_by_default():
    """Ohne traffic_shaping: kein RateShaper."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in ("peer1", "peer2", "peer3"):
            priv = X25519PrivateKey.generate()
            pub = priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            (tmp / f"{name}_x25519.pub").write_bytes(pub)

        proxy = ErebosProxy()
        server = ErebosSocks5Server(proxy, config=Socks5Config(keys_dir=tmp))
        assert server.shaper is None


def test_socks5_server_shaper_when_enabled():
    """Mit traffic_shaping=True: RateShaper mit Jitter aktiv."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in ("peer1", "peer2", "peer3"):
            priv = X25519PrivateKey.generate()
            pub = priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            (tmp / f"{name}_x25519.pub").write_bytes(pub)

        cfg = Socks5Config(
            keys_dir=tmp,
            traffic_shaping=True,
            target_rate=20.0,
            jitter_ratio=0.4,
        )
        proxy = ErebosProxy()
        server = ErebosSocks5Server(proxy, config=cfg)
        assert server.shaper is not None
        assert server.shaper.jitter_enabled is True
        assert abs(server.shaper.jitter_ratio - 0.4) < 1e-6
        assert server.shaper.target_rate == 20.0


def test_socks5_shaper_stats_reflect_config():
    """Shaper-Stats zeigen Konfiguration."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in ("peer1", "peer2", "peer3"):
            priv = X25519PrivateKey.generate()
            pub = priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            (tmp / f"{name}_x25519.pub").write_bytes(pub)

        cfg = Socks5Config(keys_dir=tmp, traffic_shaping=True)
        server = ErebosSocks5Server(ErebosProxy(), config=cfg)
        stats = server.shaper.get_stats()
        assert stats["jitter_enabled"] is True
        assert "target_rate" in stats


def test_socks5_config_max_chunk_default():
    """max_chunk default ist 65536."""
    cfg = Socks5Config()
    assert cfg.max_chunk == 65536


def test_socks5_config_custom_max_chunk():
    """max_chunk ist konfigurierbar."""
    cfg = Socks5Config(max_chunk=32768)
    assert cfg.max_chunk == 32768


# ---------------------------------------------------------------------------
# Peer-Pool + Rotation (3-Hop-Auswahl)
# ---------------------------------------------------------------------------

import tempfile
import random as _random


def _make_pool_keys(tmp: Path, names: tuple) -> None:
    """Erzeugt X25519-Keypairs für gegebene Peer-Namen in tmp."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    for name in names:
        priv = X25519PrivateKey.generate()
        pub = priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        (tmp / f"{name}_x25519.pub").write_bytes(pub)


def test_socks5_config_peer_pool_default():
    """Default-Pool = ['peer1', 'peer2', 'peer3'], strategy = 'random'."""
    cfg = Socks5Config()
    assert cfg.peer_pool == ["peer1", "peer2", "peer3"]
    assert cfg.entry_strategy == "random"


def test_socks5_config_custom_pool():
    """Custom-Pool wird respektiert."""
    cfg = Socks5Config(peer_pool=["alice", "bob", "carol", "dave", "eve"])
    assert len(cfg.peer_pool) == 5
    assert cfg.peer1_name == "alice"
    assert cfg.peer2_name == "bob"
    assert cfg.peer3_name == "carol"


def test_socks5_config_peer_pool_too_small():
    """Pool mit < 3 Peers wirft ValueError."""
    import pytest
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _make_pool_keys(tmp, ("p1", "p2"))
        cfg = Socks5Config(keys_dir=tmp, peer_pool=["p1", "p2"])
        with pytest.raises(ValueError, match="mindestens 3"):
            ErebosSocks5Server(ErebosProxy(), config=cfg)


def test_select_three_hops_first():
    """'first' liefert deterministisch die ersten 3 Pool-Einträge.

    Hinweis: entry_strategy muss explizit auf 'first' gesetzt werden,
    weil der Default jetzt 'random' ist (SPOF-Vermeidung).
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        names = ("a", "b", "c", "d", "e")
        _make_pool_keys(tmp, names)
        cfg = Socks5Config(
            keys_dir=tmp,
            peer_pool=list(names),
            entry_strategy="first",
        )
        server = ErebosSocks5Server(ErebosProxy(), config=cfg)
        for _ in range(10):
            assert server._select_three_hops() == ["a", "b", "c"]


def test_select_three_hops_random():
    """'random' liefert 3 Peers, über viele Läufe alle Pool-Peers."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        names = ("a", "b", "c", "d", "e")
        _make_pool_keys(tmp, names)
        cfg = Socks5Config(
            keys_dir=tmp, peer_pool=list(names), entry_strategy="random"
        )
        server = ErebosSocks5Server(ErebosProxy(), config=cfg)
        seen = set()
        for _ in range(200):
            hops = server._select_three_hops()
            assert len(hops) == 3
            assert len(set(hops)) == 3  # keine Duplikate
            seen.update(hops)
        assert seen == set(names), f"Nicht alle Peers gesehen: {seen}"


def test_select_three_hops_round_robin():
    """'round_robin' rotiert deterministisch."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        names = ("a", "b", "c", "d", "e")
        _make_pool_keys(tmp, names)
        cfg = Socks5Config(
            keys_dir=tmp, peer_pool=list(names), entry_strategy="round_robin"
        )
        server = ErebosSocks5Server(ErebosProxy(), config=cfg)
        seen = [tuple(server._select_three_hops()) for _ in range(5)]
        # Erwartete Sequenz: [a,b,c], [b,c,d], [c,d,e], [d,e,a], [e,a,b]
        assert seen[0] == ("a", "b", "c")
        assert seen[1] == ("b", "c", "d")
        assert seen[2] == ("c", "d", "e")
        assert seen[3] == ("d", "e", "a")
        assert seen[4] == ("e", "a", "b")


def test_backward_compat_attributes():
    """Alte Attribute (peer1_pub, peer1_port, etc.) bleiben verfügbar."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        names = ("p1", "p2", "p3")
        _make_pool_keys(tmp, names)
        cfg = Socks5Config(keys_dir=tmp, peer_pool=list(names))
        server = ErebosSocks5Server(ErebosProxy(), config=cfg)
        assert len(server.peer1_pub) == 32
        assert len(server.peer2_pub) == 32
        assert len(server.peer3_pub) == 32
        assert server.peer1_port == 9999
        assert server.peer2_port == 9998
        assert server.peer3_port == 9997
        assert server.peer1_host == "127.0.0.1"


def test_5peer_pool_rotation_reduces_bc():
    """Mit random-Rotation ist kein Peer zu dominant."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        names = ("a", "b", "c", "d", "e")
        _make_pool_keys(tmp, names)
        cfg = Socks5Config(
            keys_dir=tmp, peer_pool=list(names), entry_strategy="random"
        )
        server = ErebosSocks5Server(ErebosProxy(), config=cfg)
        # 1000 Pfade, zähle Entry-Peer-Vorkommen
        entry_counts: dict[str, int] = {n: 0 for n in names}
        for _ in range(1000):
            hops = server._select_three_hops()
            entry_counts[hops[0]] += 1
        # Alle 5 Peers sollten zwischen 10% und 30% liegen
        for name, count in entry_counts.items():
            ratio = count / 1000
            assert 0.10 < ratio < 0.30, (
                f"Peer {name} als Entry: {ratio:.2%} (erwartet 15-25%)"
            )


def test_socks5_config_default_is_random():
    """Default entry_strategy ist 'random' (SPOF-Vermeidung)."""
    cfg = Socks5Config()
    assert cfg.entry_strategy == "random"


def test_socks5_config_first_still_available():
    """'first' ist explizit verfügbar (Backward-Compat)."""
    cfg = Socks5Config(entry_strategy="first")
    assert cfg.entry_strategy == "first"
    # Und der Server nutzt es korrekt
    import tempfile
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in ("a", "b", "c"):
            priv = X25519PrivateKey.generate()
            pub = priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            (tmp / f"{name}_x25519.pub").write_bytes(pub)
        cfg = Socks5Config(
            keys_dir=tmp, peer_pool=["a", "b", "c"], entry_strategy="first"
        )
        server = ErebosSocks5Server(ErebosProxy(), config=cfg)
        for _ in range(10):
            assert server._select_three_hops() == ["a", "b", "c"]
