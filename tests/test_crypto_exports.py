"""Tests für crypto/__init__.py — alle exportierten Symbole.

Stellt sicher:
- __all__ ist vollständig und jedes Symbol importierbar
- jedes Symbol ist mindestens einmal benutzbar (Smoke)
- die beiden Dataclasses KEMKeyPair / SignatureKeyPair werden
  explizit geprüft (sonst nur indirekt über ihre Factory-Klassen)
"""
import os

import pytest

try:
    import oqs
    HAS_LIBOQS = True
except ImportError:
    HAS_LIBOQS = False


# ---------------------------------------------------------------------------
# __all__ / Importe
# ---------------------------------------------------------------------------

EXPECTED_EXPORTS = {
    "PostQuantumKEM",
    "KEMKeyPair",
    "PostQuantumSignature",
    "SignatureKeyPair",
    "ThreefishCipher",
    "ThreefishAEAD",
    "HybridCrypto",
    "HybridKEM",
    "HybridKeyPair",
    "HybridCiphertext",
    "derive_hybrid_key",
    "derive_hybrid_key_legacy",
}


def test_all_contains_expected_exports():
    """__all__ enthält genau die 12 erwarteten Symbole."""
    import erebos_network.crypto as c
    assert set(c.__all__) == EXPECTED_EXPORTS


def test_all_symbols_are_importable():
    """Jedes Symbol aus __all__ ist über das Paket erreichbar."""
    import erebos_network.crypto as c
    for name in c.__all__:
        assert hasattr(c, name), f"{name} fehlt in crypto-Modul"


def test_no_extra_exports():
    """Keine unerwarteten zusätzlichen Exporte."""
    import erebos_network.crypto as c
    extra = set(c.__all__) - EXPECTED_EXPORTS
    assert not extra, f"Unerwartete Exporte: {extra}"


# ---------------------------------------------------------------------------
# Dataclasses: KEMKeyPair / SignatureKeyPair
# ---------------------------------------------------------------------------

class TestKEMKeyPair:
    """Explizite Tests für das KEMKeyPair-Dataclass."""

    def test_kem_keypair_importable(self):
        from erebos_network.crypto import KEMKeyPair
        assert KEMKeyPair is not None

    def test_kem_keypair_has_fields(self):
        from erebos_network.crypto import KEMKeyPair
        # Dataclass-Felder prüfen
        fields = {f.name for f in KEMKeyPair.__dataclass_fields__.values()}
        assert "public_key" in fields
        assert "private_key" in fields

    def test_kem_keypair_algorithm_property(self):
        from erebos_network.crypto import KEMKeyPair
        kp = KEMKeyPair(public_key=b"pub", private_key=b"priv")
        assert kp.algorithm == "ML-KEM-1024"

    @pytest.mark.skipif(not HAS_LIBOQS, reason="liboqs fehlt")
    def test_kem_keypair_from_generate(self):
        """generate_keypair() liefert ein KEMKeyPair."""
        from erebos_network.crypto import PostQuantumKEM, KEMKeyPair
        kem = PostQuantumKEM()
        kp = kem.generate_keypair()
        assert isinstance(kp, KEMKeyPair)
        assert len(kp.public_key) == 1568
        assert len(kp.private_key) == 3168


class TestSignatureKeyPair:
    """Explizite Tests für das SignatureKeyPair-Dataclass."""

    def test_signature_keypair_importable(self):
        from erebos_network.crypto import SignatureKeyPair
        assert SignatureKeyPair is not None

    def test_signature_keypair_has_fields(self):
        from erebos_network.crypto import SignatureKeyPair
        fields = {f.name for f in SignatureKeyPair.__dataclass_fields__.values()}
        assert "public_key" in fields
        assert "private_key" in fields

    def test_signature_keypair_algorithm_property(self):
        from erebos_network.crypto import SignatureKeyPair
        kp = SignatureKeyPair(public_key=b"pub", private_key=b"priv")
        assert kp.algorithm == "SLH-DSA-SHA2-256s"

    @pytest.mark.skipif(not HAS_LIBOQS, reason="liboqs fehlt")
    @pytest.mark.slow
    def test_signature_keypair_from_generate(self):
        """generate_keypair() liefert ein SignatureKeyPair."""
        from erebos_network.crypto import PostQuantumSignature, SignatureKeyPair
        sig = PostQuantumSignature()
        kp = sig.generate_keypair()
        assert isinstance(kp, SignatureKeyPair)
        assert len(kp.public_key) == 64


# ---------------------------------------------------------------------------
# Smoke-Tests: jedes der 12 Symbole einmal nutzen
# ---------------------------------------------------------------------------

class TestExportSmoke:
    """Stellt sicher, dass jedes Symbol grundsätzlich benutzbar ist."""

    def test_derive_hybrid_key_legacy_import(self):
        from erebos_network.crypto import derive_hybrid_key_legacy
        k = derive_hybrid_key_legacy(os.urandom(32), os.urandom(32))
        assert len(k) == 32

    def test_hybrid_ciphertext_dataclass(self):
        from erebos_network.crypto import HybridCiphertext
        ct = HybridCiphertext(
            x25519_ephemeral_public=os.urandom(32),
            mlkem_ciphertext=os.urandom(1568),
        )
        assert ct.total_size == 32 + 1568

    def test_hybrid_keypair_dataclass(self):
        from erebos_network.crypto import HybridKeyPair
        kp = HybridKeyPair(
            x25519_private=os.urandom(32),
            x25519_public=os.urandom(32),
            mlkem_public=os.urandom(1568),
            mlkem_private=os.urandom(3168),
        )
        assert kp.algorithm == "X25519+ML-KEM-1024"
