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
            peer1_name="a", peer2_name="b", peer3_name="c",
            entry_port=7777, relay1_port=7778, relay2_port=7779,
        )
        server = ErebosSocks5Server(ErebosProxy(), config=cfg)
        assert server.peer1_port == 7777
        assert server.peer2_port == 7778
        assert server.peer3_port == 7779
