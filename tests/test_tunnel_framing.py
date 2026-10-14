"""Tests fuer tunnel.py - Framing, Konstanten, Key-Loading.

Netzwerk-unabhaengig: benutzt asyncio-Pipes statt echter Sockets.
"""

import asyncio
import struct

import pytest

from pathlib import Path

from erebos_network.tunnel import (
    FRAME_RELAY,
    FRAME_OPEN,
    FRAME_DATA,
    PORT_TO_PEER_NAME,
    MAX_FRAME,
    KEYS_DIR,
    _load_or_create_keypair,
    _derive_key,
    _send_frame,
    _recv_frame,
    _handle_exit,
    _handle_relay,
    ErebosTunnelClient,
    run_peer_server,
)


# ---- Konstanten ----

def test_frame_types_distinct():
    """Die drei Frame-Typen sind unterscheidbar."""
    assert FRAME_RELAY != FRAME_OPEN
    assert FRAME_OPEN != FRAME_DATA
    assert FRAME_RELAY != FRAME_DATA


def test_frame_types_values():
    """Frame-Typen haben die dokumentierten Werte."""
    assert FRAME_RELAY == 0x01
    assert FRAME_OPEN == 0x02
    assert FRAME_DATA == 0x03


def test_port_to_peer_name_covers_all():
    """Alle drei Peer-Ports sind gemappt."""
    assert PORT_TO_PEER_NAME[9997] == "peer3"
    assert PORT_TO_PEER_NAME[9998] == "peer2"
    assert PORT_TO_PEER_NAME[9999] == "peer1"


def test_max_frame_positive():
    """MAX_FRAME ist gesetzt."""
    assert MAX_FRAME > 0


# ---- Key-Loading ----

@pytest.mark.parametrize("name", ["peer1", "peer2", "peer3"])
def test_load_existing_keypairs(name):
    """Alle drei Peer-Keypairs lassen sich laden."""
    ed_priv, x_priv, ed_pub, x_pub = _load_or_create_keypair(name)
    assert len(ed_pub) == 32
    assert len(x_pub) == 32


def test_load_missing_keypair_fails():
    """Fehlender Key wirft FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        _load_or_create_keypair("nonexistent_peer_xyz")


# ---- HKDF ----

def test_derive_key_length():
    """HKDF liefert 32 Byte."""
    key = _derive_key(b"shared_secret_input")
    assert len(key) == 32


def test_derive_key_deterministic():
    """Gleicher Input -> gleicher Key."""
    k1 = _derive_key(b"same_input")
    k2 = _derive_key(b"same_input")
    assert k1 == k2


def test_derive_key_differs_per_input():
    """Unterschiedlicher Input -> unterschiedlicher Key."""
    k1 = _derive_key(b"input_a")
    k2 = _derive_key(b"input_b")
    assert k1 != k2


# ---- Framing ueber asyncio-Pipe ----

@pytest.mark.asyncio
async def test_frame_roundtrip_small():
    """Kleiner Frame Roundtrip."""
    reader = asyncio.StreamReader()
    # StreamWriter-Ersatz: schreibt in den Reader
    class FakeWriter:
        def __init__(self, reader):
            self.reader = reader
        def write(self, data):
            self.reader.feed_data(data)
        async def drain(self):
            pass

    writer = FakeWriter(reader)
    payload = b"hello world"
    await _send_frame(writer, payload)
    received = await _recv_frame(reader)
    assert received == payload


@pytest.mark.asyncio
async def test_frame_roundtrip_empty():
    """Leerer Frame Roundtrip."""
    reader = asyncio.StreamReader()
    class FakeWriter:
        def __init__(self, reader):
            self.reader = reader
        def write(self, data):
            self.reader.feed_data(data)
        async def drain(self):
            pass

    writer = FakeWriter(reader)
    await _send_frame(writer, b"")
    received = await _recv_frame(reader)
    assert received == b""


@pytest.mark.asyncio
async def test_frame_roundtrip_large():
    """Grosser Frame (bis MAX_FRAME)."""
    reader = asyncio.StreamReader()
    class FakeWriter:
        def __init__(self, reader):
            self.reader = reader
        def write(self, data):
            self.reader.feed_data(data)
        async def drain(self):
            pass

    writer = FakeWriter(reader)
    payload = b"x" * 50000
    await _send_frame(writer, payload)
    received = await _recv_frame(reader)
    assert received == payload


@pytest.mark.asyncio
async def test_frame_length_prefix_correct():
    """Das 4-Byte Laengenpraefix ist big-endian und korrekt."""
    reader = asyncio.StreamReader()
    class FakeWriter:
        def __init__(self, reader):
            self.reader = reader
        def write(self, data):
            self.reader.feed_data(data)
        async def drain(self):
            pass

    writer = FakeWriter(reader)
    payload = b"abc"
    await _send_frame(writer, payload)
    # Erste 4 Bytes = Laenge
    header = await reader.readexactly(4)
    length = struct.unpack("!I", header)[0]
    assert length == 3
    # Rest = payload
    body = await reader.readexactly(3)
    assert body == b"abc"


@pytest.mark.asyncio
async def test_frame_multiple_in_sequence():
    """Mehrere Frames hintereinander lesen."""
    reader = asyncio.StreamReader()
    class FakeWriter:
        def __init__(self, reader):
            self.reader = reader
        def write(self, data):
            self.reader.feed_data(data)
        async def drain(self):
            pass

    writer = FakeWriter(reader)
    payloads = [b"one", b"two", b"three"]
    for p in payloads:
        await _send_frame(writer, p)
    received = []
    for _ in payloads:
        received.append(await _recv_frame(reader))
    assert received == payloads


# ---- API-Existenz (Smoke-Tests) ----

def test_public_api_exists():
    """Die oeffentlichen Funktionen/Klassen existieren."""
    assert callable(_send_frame)
    assert callable(_recv_frame)
    assert callable(_handle_exit)
    assert callable(_handle_relay)
    assert callable(run_peer_server)
    assert isinstance(ErebosTunnelClient, type)


# ---------------------------------------------------------------------------
# liboqs-Guard (Härtung: kein stiller Totalausfall ohne liboqs)
# ---------------------------------------------------------------------------

def test_has_liboqs_flag_exists():
    """tunnel.py exportiert HAS_LIBOQS."""
    from erebos_network.tunnel import HAS_LIBOQS
    assert isinstance(HAS_LIBOQS, bool)


def test_mlkem_load_fails_without_liboqs(monkeypatch):
    """Ohne liboqs: _load_mlkem_keypair wirft klare RuntimeError."""
    import pytest
    from erebos_network import tunnel

    monkeypatch.setattr(tunnel, "HAS_LIBOQS", False)
    with pytest.raises(RuntimeError, match="liboqs nicht verfuegbar"):
        tunnel._load_mlkem_keypair("client")


def test_connect_fails_without_liboqs(monkeypatch):
    """Ohne liboqs: connect() wirft RuntimeError statt ImportError."""
    import asyncio
    import pytest
    from erebos_network import tunnel

    monkeypatch.setattr(tunnel, "HAS_LIBOQS", False)
    client = tunnel.ErebosTunnelClient(host="127.0.0.1", port=9999)
    with pytest.raises(RuntimeError, match="liboqs nicht verfuegbar"):
        asyncio.run(client.connect(peer_name="peer1"))


def test_module_imports_without_liboqs(monkeypatch):
    """tunnel.py bleibt importierbar, auch wenn liboqs fehlt."""
    import importlib
    import sys

    # Modul aus Cache entfernen
    mod_name = "erebos_network.tunnel"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    # Import simulieren ohne liboqs
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "oqs":
            raise ImportError("simulated: no liboqs")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    try:
        mod = importlib.import_module(mod_name)
        assert mod.HAS_LIBOQS is False
        assert mod.oqs is None
    finally:
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        # Original neu laden
        importlib.import_module(mod_name)
