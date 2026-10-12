"""Tests für Post-Quanten-Kryptographie."""

import os

import pytest

from erebos_network.crypto import (
    HybridCrypto,
    PostQuantumKEM,
    PostQuantumSignature,
    ThreefishCipher,
)


def test_kem_sizes():
    """ML-KEM-1024 Größen stimmen."""
    sizes = PostQuantumKEM.sizes()
    assert sizes["algorithm"] == "ML-KEM-1024"
    assert sizes["public_key"] == 1568
    assert sizes["private_key"] == 3168
    assert sizes["shared_secret"] == 32
    assert sizes["nist_level"] == 5


def test_sig_sizes():
    """SLH-DSA Größen stimmen."""
    sizes = PostQuantumSignature.sizes()
    assert sizes["algorithm"] == "SLH-DSA-SHA2-256s"
    assert sizes["public_key"] == 64
    assert sizes["nist_level"] == 5


def test_threefish_sizes():
    """Threefish-512 Größen stimmen."""
    sizes = ThreefishCipher.sizes()
    assert sizes["algorithm"] == "Threefish-512"
    assert sizes["key"] == 64
    assert sizes["block"] == 64
    assert sizes["post_quantum_security"] == 256


def test_threefish_key_length():
    """Threefish Key muss 64 Bytes sein."""
    with pytest.raises(ValueError):
        ThreefishCipher(key=b"short", tweak=os.urandom(16))


def test_threefish_generate():
    """Threefish Key wird generiert."""
    cipher = ThreefishCipher.generate()
    assert len(cipher.key) == 64
    assert len(cipher.tweak) == 16


def test_hybrid_sizes():
    """Hybrid-Größen stimmen."""
    sizes = HybridCrypto.sizes()
    assert sizes["hybrid"]["nist_level"] == 5
    assert sizes["hybrid"]["post_quantum_security"] == 256
