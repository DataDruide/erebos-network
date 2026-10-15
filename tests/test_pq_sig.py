"""Tests für crypto/pq_sig.py (SLH-DSA).

Hinweis: SLH-DSA-SHA2-256s ist sehr langsam (Key-Gen + Sign ~1-2s pro Op).
Langsame Tests sind mit @pytest.mark.slow markiert und werden per Default
uebersprungen. Ausfuehren mit: pytest -m slow
"""
import pytest

try:
    import oqs
    HAS_LIBOQS = True
except ImportError:
    HAS_LIBOQS = False

pytestmark = pytest.mark.skipif(not HAS_LIBOQS, reason="liboqs fehlt")


def test_sizes():
    """SLH-DSA Größen (schnell, kein Crypto-Op)."""
    from erebos_network.crypto.pq_sig import PostQuantumSignature
    sizes = PostQuantumSignature.sizes()
    assert sizes["algorithm"] == "SLH-DSA-SHA2-256s"
    assert sizes["public_key"] == 64
    assert sizes["private_key"] == 128
    assert sizes["nist_level"] == 5


def test_sign_wrong_private_key_len():
    """Falsche Private-Key-Länge -> ValueError (schnell)."""
    from erebos_network.crypto.pq_sig import PostQuantumSignature
    sig = PostQuantumSignature()
    with pytest.raises(ValueError, match="private_key"):
        sig.sign(b"msg", b"short")


def test_verify_wrong_public_key_len():
    """Falsche Public-Key-Länge -> ValueError (schnell)."""
    from erebos_network.crypto.pq_sig import PostQuantumSignature
    sig = PostQuantumSignature()
    with pytest.raises(ValueError, match="public_key"):
        sig.verify(b"msg", b"sig", b"short")


@pytest.mark.slow
def test_sign_verify_roundtrip():
    """Signieren und Verifizieren (langsam: ~5s)."""
    from erebos_network.crypto.pq_sig import PostQuantumSignature
    sig = PostQuantumSignature()
    kp = sig.generate_keypair()
    msg = b"hello erebos"
    signature = sig.sign(msg, kp.private_key)
    assert len(signature) == PostQuantumSignature.SIGNATURE_LEN
    assert sig.verify(msg, signature, kp.public_key) is True
    assert sig.verify(b"tampered", signature, kp.public_key) is False


@pytest.mark.slow
def test_signature_unique():
    """SLH-DSA ist randomisiert (langsam: ~10s)."""
    from erebos_network.crypto.pq_sig import PostQuantumSignature
    sig = PostQuantumSignature()
    kp = sig.generate_keypair()
    s1 = sig.sign(b"msg", kp.private_key)
    s2 = sig.sign(b"msg", kp.private_key)
    assert s1 != s2, "SLH-DSA in liboqs ist randomisiert"
    assert sig.verify(b"msg", s1, kp.public_key) is True
    assert sig.verify(b"msg", s2, kp.public_key) is True
