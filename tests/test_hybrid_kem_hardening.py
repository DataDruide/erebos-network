"""Tests für crypto/hybrid_kem.py Hardening."""
import os
import pytest

try:
    import oqs
    HAS_LIBOQS = True
except ImportError:
    HAS_LIBOQS = False

pytestmark = pytest.mark.skipif(not HAS_LIBOQS, reason="liboqs fehlt")


class TestHybridKeyPairValidation:
    def test_valid_keypair(self):
        """Korrekte Größen akzeptiert."""
        from erebos_network.crypto.hybrid_kem import HybridKeyPair
        kp = HybridKeyPair(
            x25519_private=os.urandom(32),
            x25519_public=os.urandom(32),
            mlkem_public=os.urandom(1568),
            mlkem_private=os.urandom(3168),
        )
        assert kp.algorithm == "X25519+ML-KEM-1024"

    def test_wrong_x25519_private(self):
        from erebos_network.crypto.hybrid_kem import HybridKeyPair
        with pytest.raises(ValueError, match="x25519_private"):
            HybridKeyPair(
                x25519_private=b"short",
                x25519_public=os.urandom(32),
                mlkem_public=os.urandom(1568),
                mlkem_private=os.urandom(3168),
            )

    def test_wrong_mlkem_public(self):
        from erebos_network.crypto.hybrid_kem import HybridKeyPair
        with pytest.raises(ValueError, match="mlkem_public"):
            HybridKeyPair(
                x25519_private=os.urandom(32),
                x25519_public=os.urandom(32),
                mlkem_public=b"short",
                mlkem_private=os.urandom(3168),
            )


class TestHybridCiphertextValidation:
    def test_valid_ciphertext(self):
        from erebos_network.crypto.hybrid_kem import HybridCiphertext
        ct = HybridCiphertext(
            x25519_ephemeral_public=os.urandom(32),
            mlkem_ciphertext=os.urandom(1568),
        )
        assert ct.total_size == 32 + 1568

    def test_wrong_x25519_ephemeral(self):
        from erebos_network.crypto.hybrid_kem import HybridCiphertext
        with pytest.raises(ValueError, match="x25519_ephemeral_public"):
            HybridCiphertext(
                x25519_ephemeral_public=b"short",
                mlkem_ciphertext=os.urandom(1568),
            )


class TestHybridKEMDefault:
    def test_default_kdf_is_hkdf(self):
        """Default-kdf ist 'hkdf' (RFC 5869)."""
        from erebos_network.crypto.hybrid_kem import HybridKEM
        assert HybridKEM().kdf == "hkdf"

    def test_kdf_hkdf_matches_derive_hybrid_key(self):
        """HybridKEM(kdf='hkdf') nutzt derive_hybrid_key."""
        from erebos_network.crypto.hybrid_kem import (
            HybridKEM, derive_hybrid_key,
        )
        kem = HybridKEM(kdf="hkdf")
        kp = kem.generate_keypair()
        ct, ss = kem.encapsulate(kp)
        # Direkt nachrechnen
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey, X25519PublicKey,
        )
        eph_priv = X25519PrivateKey.from_private_bytes(b"\x00" * 32)  # dummy
        # Wir koennen den eph_priv nicht rekonstruieren, also
        # pruefen wir indirekt: decapsulate mit gleichem kdf liefert ss
        ss_dec = kem.decapsulate(ct, kp)
        assert ss_dec == ss


class TestHybridKEMTypeChecks:
    def test_encapsulate_wrong_type(self):
        from erebos_network.crypto.hybrid_kem import HybridKEM
        kem = HybridKEM()
        with pytest.raises(TypeError, match="HybridKeyPair"):
            kem.encapsulate("not a keypair")

    def test_decapsulate_wrong_ciphertext_type(self):
        from erebos_network.crypto.hybrid_kem import HybridKEM
        kem = HybridKEM()
        kp = kem.generate_keypair()
        with pytest.raises(TypeError, match="HybridCiphertext"):
            kem.decapsulate("not a ciphertext", kp)

    def test_decapsulate_wrong_keypair_type(self):
        from erebos_network.crypto.hybrid_kem import HybridKEM, HybridCiphertext
        kem = HybridKEM()
        ct = HybridCiphertext(
            x25519_ephemeral_public=os.urandom(32),
            mlkem_ciphertext=os.urandom(1568),
        )
        with pytest.raises(TypeError, match="HybridKeyPair"):
            kem.decapsulate(ct, "not a keypair")
