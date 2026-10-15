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


# ---------------------------------------------------------------------------
# ThreefishAEAD (CTR + HMAC)
# ---------------------------------------------------------------------------

class TestThreefishAEAD:
    def test_aead_sizes(self):
        """ThreefishAEAD-Größen."""
        from erebos_network.crypto import ThreefishAEAD
        sizes = ThreefishAEAD.sizes()
        assert sizes["key"] == 64
        assert sizes["nonce"] == 16
        assert sizes["tag"] == 32
        assert sizes["mode"] == "CTR"

    def test_aead_roundtrip(self):
        """Encrypt/Decrypt Roundtrip."""
        from erebos_network.crypto import ThreefishAEAD
        import os
        aead = ThreefishAEAD.from_secret(os.urandom(32))
        for size in (0, 1, 64, 100, 1000):
            pt = os.urandom(size)
            ct = aead.encrypt(pt)
            assert aead.decrypt(ct) == pt, f"Roundtrip bei size={size}"

    def test_aead_tamper_detection(self):
        """Manipulation wird erkannt."""
        import pytest
        from erebos_network.crypto import ThreefishAEAD
        import os
        aead = ThreefishAEAD.from_secret(os.urandom(32))
        ct = bytearray(aead.encrypt(b"geheim"))
        ct[-1] ^= 0x01  # Tag manipulieren
        with pytest.raises(ValueError, match="MAC"):
            aead.decrypt(bytes(ct))

    def test_aead_unique_ciphertexts(self):
        """Nonce ist zufällig -> verschiedene Ciphertexte."""
        from erebos_network.crypto import ThreefishAEAD
        import os
        aead = ThreefishAEAD.from_secret(os.urandom(32))
        ct1 = aead.encrypt(b"same")
        ct2 = aead.encrypt(b"same")
        assert ct1 != ct2

    def test_aead_no_patterns(self):
        """Gleiche Blöcke -> verschiedene Ciphertext-Blöcke (CTR)."""
        from erebos_network.crypto import ThreefishAEAD
        import os
        aead = ThreefishAEAD.from_secret(os.urandom(32))
        pt = b"A" * 64 + b"A" * 64  # zwei gleiche Blöcke
        ct = aead.encrypt(pt)
        block1 = ct[16:16+64]
        block2 = ct[16+64:16+128]
        assert block1 != block2, "ECB-Muster erkannt!"

    def test_aead_hkdf_from_secret(self):
        """from_secret leitet deterministisch ab."""
        from erebos_network.crypto import ThreefishAEAD
        secret = b"x" * 32
        a1 = ThreefishAEAD.from_secret(secret)
        a2 = ThreefishAEAD.from_secret(secret)
        assert a1.key == a2.key
        assert a1.mac_key == a2.mac_key

    def test_aead_wrong_key_fails(self):
        """Falscher Key -> MAC-Fehler."""
        import pytest
        from erebos_network.crypto import ThreefishAEAD
        import os
        a1 = ThreefishAEAD.from_secret(b"a" * 32)
        a2 = ThreefishAEAD.from_secret(b"b" * 32)
        ct = a1.encrypt(b"data")
        with pytest.raises(ValueError, match="MAC"):
            a2.decrypt(ct)
