"""Tests fuer Hygiene, Hardening, Pfad-Auswahl und PQ-Sphinx."""

import asyncio

import pytest

from erebos_network.hygiene import HygieneConfig, HygieneManager
from erebos_network.hardening import HardeningConfig, MemoryHardening
from erebos_network.path_selection import (
    MixNode,
    PathSelectionConfig,
    PathSelector,
)
from erebos_network.crypto.pq_kem import PostQuantumKEM
from erebos_network.crypto.pq_sphinx import PQHop, PQSphinx


# --- Hygiene Tests ---

@pytest.mark.asyncio
async def test_hygiene_schedule_request():
    """Hygiene plant eine Anfrage."""
    config = HygieneConfig(min_delay_ms=0, max_delay_ms=10)
    h = HygieneManager(config)
    meta = await h.schedule_request()
    assert meta.request_id
    assert meta.sent_at >= meta.created_at


def test_hygiene_pad_request():
    """Hygiene polstert Anfragen."""
    config = HygieneConfig(padding_enabled=True, padding_block_size=1024)
    h = HygieneManager(config)
    padded = h.pad_request(b"hello")
    assert len(padded) == 1024


def test_hygiene_no_pad():
    """Hygiene polstert nicht, wenn deaktiviert."""
    config = HygieneConfig(padding_enabled=False)
    h = HygieneManager(config)
    data = b"hello"
    assert h.pad_request(data) == data


def test_hygiene_rate_limit():
    """Hygiene Rate-Limit funktioniert."""
    config = HygieneConfig(max_requests_per_minute=5)
    h = HygieneManager(config)
    for _ in range(5):
        assert h.check_rate_limit() is True
    assert h.check_rate_limit() is False


# --- Hardening Tests ---

def test_hardening_add_descriptor():
    """Hardening fuegt Descriptor hinzu."""
    h = MemoryHardening()
    assert h.add_descriptor("peer1", "d1", b"data") is True
    assert h.total_descriptors == 1


def test_hardening_reject_oversized():
    """Hardening lehnt zu grosse Descriptors ab."""
    config = HardeningConfig(max_descriptor_size=100)
    h = MemoryHardening(config)
    assert h.add_descriptor("peer1", "d1", b"x" * 200) is False
    assert h.stats["descriptors_rejected_size"] == 1


def test_hardening_reject_too_many():
    """Hardening lehnt zu viele Descriptors pro Peer ab."""
    config = HardeningConfig(max_descriptors_per_peer=3)
    h = MemoryHardening(config)
    for i in range(3):
        h.add_descriptor("peer1", f"d{i}", b"data")
    assert h.add_descriptor("peer1", "d4", b"data") is False


def test_hardening_rate_limit():
    """Hardening Rate-Limit funktioniert."""
    config = HardeningConfig(rate_limit_per_minute=3)
    h = MemoryHardening(config)
    for _ in range(3):
        assert h.check_rate_limit("peer1") is True
    assert h.check_rate_limit("peer1") is False


def test_hardening_cleanup():
    """Hardening cleanup entfernt abgelaufene Descriptors."""
    config = HardeningConfig(descriptor_ttl_seconds=0)
    h = MemoryHardening(config)
    h.add_descriptor("peer1", "d1", b"data")
    removed = h.cleanup(force=True)
    assert removed == 1


# --- Path Selection Tests ---

def make_nodes(n: int = 10) -> list[MixNode]:
    """Erzeugt n Test-Nodes."""
    return [
        MixNode(
            node_id=f"node{i}",
            address=f"127.0.0.1:{8000+i}",
            reputation=0.5 + (i * 0.05),
        )
        for i in range(n)
    ]


def test_path_selection_random():
    """Random-Strategie waehlt Pfad."""
    config = PathSelectionConfig(strategy="random", num_hops=3)
    ps = PathSelector(config)
    path = ps.select_path(make_nodes(10))
    assert len(path) == 3


def test_path_selection_k_hf():
    """K-HF-Strategie waehlt Pfad."""
    config = PathSelectionConfig(strategy="k_hf", num_hops=3)
    ps = PathSelector(config)
    path = ps.select_path(make_nodes(10))
    assert len(path) == 3


def test_path_selection_k_over_w():
    """K/W-Strategie waehlt Pfad."""
    config = PathSelectionConfig(strategy="k_over_w", num_hops=3)
    ps = PathSelector(config)
    path = ps.select_path(make_nodes(10))
    assert len(path) == 3


def test_path_selection_alpha_ss():
    """alpha-SS-Strategie waehlt Pfad."""
    config = PathSelectionConfig(strategy="alpha_ss", num_hops=3)
    ps = PathSelector(config)
    path = ps.select_path(make_nodes(10))
    assert len(path) == 3


def test_path_selection_too_few_nodes():
    """Zu wenige Nodes wirft Fehler."""
    config = PathSelectionConfig(num_hops=5)
    ps = PathSelector(config)
    with pytest.raises(ValueError):
        ps.select_path(make_nodes(3))


# --- PQ-Sphinx Tests ---

def test_pq_sphinx_sizes():
    """PQ-Sphinx Groessen stimmen."""
    sizes = PQSphinx.sizes(3)
    assert sizes["num_hops"] == 3
    assert sizes["nist_level"] == 5
    assert sizes["algorithm"] == "PQ-Sphinx (ML-KEM-1024)"


def test_pq_sphinx_create_packet():
    """PQ-Sphinx erzeugt Paket."""
    kem = PostQuantumKEM()
    hops = []
    for i in range(3):
        kp = kem.generate_keypair()
        hops.append(PQHop(
            node_id=f"node{i}",
            public_key=kp.public_key,
        ))

    sphinx = PQSphinx()
    packet = sphinx.create_packet(hops, b"Hello, Erebos!")
    assert packet.num_hops == 3
    assert len(packet.mac) == 32
    assert packet.total_size > 0


def test_pq_sphinx_xor_encrypt():
    """ChaCha20-Poly1305 Encrypt/Decrypt Roundtrip.

    Hinweis: _xor_encrypt ist jetzt AEAD (nicht mehr XOR). Der Test
    nutzt daher _xor_decrypt fuer den Roundtrip.
    """
    sphinx = PQSphinx()
    key = b"x" * 32
    data = b"test data"
    encrypted = sphinx._xor_encrypt(data, key)
    assert encrypted != data
    # AEAD: 12 Byte Nonce + len(data) + 16 Byte Poly1305-Tag
    assert len(encrypted) == 12 + len(data) + 16
    decrypted = sphinx._xor_decrypt(encrypted, key)
    assert decrypted == data


def test_pq_sphinx_aead_tamper_detection():
    """ChaCha20-Poly1305 erkennt manipulierte Ciphertexte."""
    import pytest
    from cryptography.exceptions import InvalidTag

    sphinx = PQSphinx()
    key = b"y" * 32
    data = b"payload"
    encrypted = bytearray(sphinx._xor_encrypt(data, key))
    # Letztes Byte manipulieren (Poly1305-Tag)
    encrypted[-1] ^= 0x01

    with pytest.raises(InvalidTag):
        sphinx._xor_decrypt(bytes(encrypted), key)


def test_pq_sphinx_aead_unique_ciphertexts():
    """Zwei Encrypts mit demselben Key liefern unterschiedliche Ciphertexte.

    (Nonce ist zufaellig.)
    """
    sphinx = PQSphinx()
    key = b"z" * 32
    data = b"same data"
    ct1 = sphinx._xor_encrypt(data, key)
    ct2 = sphinx._xor_encrypt(data, key)
    assert ct1 != ct2, "Nonce muss zufaellig sein"
