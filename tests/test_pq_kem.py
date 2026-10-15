"""Tests für crypto/pq_kem.py (ML-KEM-1024)."""
import pytest

try:
    import oqs
    HAS_LIBOQS = True
except ImportError:
    HAS_LIBOQS = False

pytestmark = pytest.mark.skipif(not HAS_LIBOQS, reason="liboqs fehlt")


def test_sizes():
    """ML-KEM-1024 Größen."""
    from erebos_network.crypto.pq_kem import PostQuantumKEM
    sizes = PostQuantumKEM.sizes()
    assert sizes["algorithm"] == "ML-KEM-1024"
    assert sizes["public_key"] == 1568
    assert sizes["private_key"] == 3168
    assert sizes["nist_level"] == 5


def test_generate_keypair_correct_sizes():
    """Keypair-Generierung liefert korrekte Größen."""
    from erebos_network.crypto.pq_kem import PostQuantumKEM
    kem = PostQuantumKEM()
    kp = kem.generate_keypair()
    assert len(kp.public_key) == PostQuantumKEM.PUBLIC_KEY_LEN
    assert len(kp.private_key) == PostQuantumKEM.PRIVATE_KEY_LEN


def test_roundtrip():
    """encapsulate + decapsulate liefert dasselbe Shared Secret."""
    from erebos_network.crypto.pq_kem import PostQuantumKEM
    kem = PostQuantumKEM()
    kp = kem.generate_keypair()

    ct, ss_enc = kem.encapsulate(kp.public_key)
    assert len(ct) == PostQuantumKEM.CIPHERTEXT_LEN
    assert len(ss_enc) == PostQuantumKEM.SHARED_SECRET_LEN

    ss_dec = kem.decapsulate(ct, kp.private_key)
    assert ss_dec == ss_enc


def test_two_keypairs_independent():
    """Zwei Keypairs liefern unterschiedliche Shared Secrets."""
    from erebos_network.crypto.pq_kem import PostQuantumKEM
    kem = PostQuantumKEM()
    kp1 = kem.generate_keypair()
    kp2 = kem.generate_keypair()
    assert kp1.public_key != kp2.public_key
    assert kp1.private_key != kp2.private_key


def test_encapsulate_wrong_pubkey_len():
    """Falsche Public-Key-Länge -> ValueError."""
    from erebos_network.crypto.pq_kem import PostQuantumKEM
    kem = PostQuantumKEM()
    with pytest.raises(ValueError, match="public_key"):
        kem.encapsulate(b"short")


def test_decapsulate_wrong_privkey_len():
    """Falsche Private-Key-Länge -> ValueError."""
    from erebos_network.crypto.pq_kem import PostQuantumKEM
    kem = PostQuantumKEM()
    with pytest.raises(ValueError, match="private_key"):
        kem.decapsulate(b"ct", b"short")


def test_decapsulate_wrong_ct_len():
    """Falsche Ciphertext-Länge -> ValueError."""
    from erebos_network.crypto.pq_kem import PostQuantumKEM
    kem = PostQuantumKEM()
    kp = kem.generate_keypair()
    with pytest.raises(ValueError, match="ciphertext"):
        kem.decapsulate(b"short", kp.private_key)


def test_decapsulate_wrong_key_wrong_ss():
    """Falscher Private Key liefert anderes Shared Secret (kein Crash)."""
    from erebos_network.crypto.pq_kem import PostQuantumKEM
    kem = PostQuantumKEM()
    kp1 = kem.generate_keypair()
    kp2 = kem.generate_keypair()

    ct, ss_enc = kem.encapsulate(kp1.public_key)
    # Mit falschem Key: ML-KEM liefert deterministisch "Zufalls"-SS
    # (kein Fehler — implizite Ablehnung).
    ss_wrong = kem.decapsulate(ct, kp2.private_key)
    assert ss_wrong != ss_enc
