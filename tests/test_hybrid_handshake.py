"""Tests fuer den Hybrid-Handshake (X25519 + ML-KEM-1024) im Tunnel.

Prueft die Bausteine ohne echte Sockets:
- ML-KEM Keypair generieren und laden
- Encapsulate/Decapsulate Shared Secret
- Kombinierter Handshake (X25519 + ML-KEM -> HKDF)
- Signatur ueber (x_pub || mlkem_pub)
- Symmetrie: Client und Peer berechnen denselben Session-Key
"""

import os
from pathlib import Path

import pytest

import oqs
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


KEYS_DIR = Path(__file__).parent.parent / "erebos_keys"


# ---- Hilfsfunktionen (spaeter in tunnel.py) ----

def _raw_priv(key) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _raw_pub(key) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _derive_key_pq(x25519_shared: bytes, mlkem_shared: bytes) -> bytes:
    """Kombiniert X25519 + ML-KEM-1024 Shared Secrets zu 32 Byte."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"erebos-tunnel-pq-v1",
    ).derive(x25519_shared + mlkem_shared)


# ---- ML-KEM Basis ----

def test_mlkem_keypair_generates():
    """ML-KEM-1024 Keypair kann generiert werden."""
    with oqs.KeyEncapsulation("ML-KEM-1024") as kem:
        pub = kem.generate_keypair()
        priv = kem.export_secret_key()
    assert len(pub) == 1568
    assert len(priv) == 3168


def test_mlkem_encap_decap():
    """Encapsulate + Decapsulate liefert dasselbe Secret."""
    with oqs.KeyEncapsulation("ML-KEM-1024") as kem:
        pub = kem.generate_keypair()
        priv = kem.export_secret_key()

    with oqs.KeyEncapsulation("ML-KEM-1024") as enc:
        ct, shared_enc = enc.encap_secret(pub)

    with oqs.KeyEncapsulation("ML-KEM-1024", priv) as dec:
        shared_dec = dec.decap_secret(ct)

    assert shared_enc == shared_dec
    assert len(shared_enc) == 32


def test_mlkem_project_keys_loadable():
    """Die generierten ML-KEM-Projektkeys sind ladbar."""
    for name in ("client", "peer1", "peer2", "peer3"):
        priv = (KEYS_DIR / f"{name}_mlkem").read_bytes()
        pub = (KEYS_DIR / f"{name}_mlkem.pub").read_bytes()
        assert len(priv) == 3168, f"{name} priv falsche Groesse"
        assert len(pub) == 1568, f"{name} pub falsche Groesse"


# ---- Signatur ueber (x_pub || mlkem_pub) ----

def test_signature_covers_both_pubkeys():
    """Signatur deckt X25519-Pubkey UND ML-KEM-Pubkey."""
    ed = Ed25519PrivateKey.generate()
    x = X25519PrivateKey.generate()

    with oqs.KeyEncapsulation("ML-KEM-1024") as kem:
        mlkem_pub = kem.generate_keypair()

    x_pub = _raw_pub(x)
    signed_data = x_pub + mlkem_pub
    sig = ed.sign(signed_data)

    assert len(sig) == 64

    # Verifikation mit korrekten Daten
    ed.public_key().verify(sig, signed_data)

    # Manipulierte mlkem_pub schlaegt fehl
    with pytest.raises(Exception):
        ed.public_key().verify(sig, x_pub + b"\x00" * 1568)


# ---- Kombinierter Schluessel ----

def test_derive_key_pq_deterministic():
    """HKDF ueber x25519+mlkem ist deterministisch."""
    x_shared = os.urandom(32)
    mlkem_shared = os.urandom(32)
    k1 = _derive_key_pq(x_shared, mlkem_shared)
    k2 = _derive_key_pq(x_shared, mlkem_shared)
    assert k1 == k2
    assert len(k1) == 32


def test_derive_key_pq_differs_on_mlkem():
    """Unterschiedliches ML-KEM-Secret -> unterschiedlicher Key."""
    x_shared = os.urandom(32)
    k1 = _derive_key_pq(x_shared, os.urandom(32))
    k2 = _derive_key_pq(x_shared, os.urandom(32))
    assert k1 != k2


def test_derive_key_pq_differs_on_x25519():
    """Unterschiedliches X25519-Secret -> unterschiedlicher Key."""
    mlkem_shared = os.urandom(32)
    k1 = _derive_key_pq(os.urandom(32), mlkem_shared)
    k2 = _derive_key_pq(os.urandom(32), mlkem_shared)
    assert k1 != k2


# ---- Volle Hybrid-Handshake-Sequenz ----

def test_full_hybrid_handshake():
    """Client und Peer leiten denselben Session-Key ab."""
    # Peer-Identitaet
    peer_ed = Ed25519PrivateKey.generate()
    peer_x = X25519PrivateKey.generate()
    with oqs.KeyEncapsulation("ML-KEM-1024") as kem:
        peer_mlkem_pub = kem.generate_keypair()
        peer_mlkem_priv = kem.export_secret_key()

    # Client kennt peer_x_pub und peer_mlkem_pub
    peer_x_pub = _raw_pub(peer_x)

    # === Client-Seite ===
    client_x = X25519PrivateKey.generate()
    client_x_pub = _raw_pub(client_x)

    with oqs.KeyEncapsulation("ML-KEM-1024") as enc:
        mlkem_ct, client_mlkem_shared = enc.encap_secret(peer_mlkem_pub)

    # Der Client sendet: x_pub || mlkem_ct, signiert mit eigener Ed25519
    # (in echter Implementierung signiert der Client ueber seine eigenen Pubkeys)
    # Hier nur: der Peer empfaengt mlkem_ct

    # === Peer-Seite ===
    with oqs.KeyEncapsulation("ML-KEM-1024", peer_mlkem_priv) as dec:
        peer_mlkem_shared = dec.decap_secret(mlkem_ct)

    # X25519 beidseitig
    client_x_shared = client_x.exchange(peer_x.public_key())
    peer_x_shared = peer_x.exchange(X25519PublicKey.from_public_bytes(client_x_pub))

    assert client_x_shared == peer_x_shared
    assert client_mlkem_shared == peer_mlkem_shared

    # Session-Key
    client_key = _derive_key_pq(client_x_shared, client_mlkem_shared)
    peer_key = _derive_key_pq(peer_x_shared, peer_mlkem_shared)
    assert client_key == peer_key


def test_hybrid_session_encryption():
    """Beide Seiten koennen mit dem abgeleiteten Key verschluesseln."""
    # Aus vorherigem Test bekannte Symmetrie vorausgesetzt
    a_priv = X25519PrivateKey.generate()
    b_priv = X25519PrivateKey.generate()

    with oqs.KeyEncapsulation("ML-KEM-1024") as kem:
        mlkem_pub = kem.generate_keypair()
        mlkem_priv = kem.export_secret_key()

    with oqs.KeyEncapsulation("ML-KEM-1024") as enc:
        ct, a_mlkem = enc.encap_secret(mlkem_pub)
    with oqs.KeyEncapsulation("ML-KEM-1024", mlkem_priv) as dec:
        b_mlkem = dec.decap_secret(ct)

    a_x = a_priv.exchange(b_priv.public_key())
    b_x = b_priv.exchange(a_priv.public_key())

    a_key = _derive_key_pq(a_x, a_mlkem)
    b_key = _derive_key_pq(b_x, b_mlkem)

    cipher_a = ChaCha20Poly1305(a_key)
    cipher_b = ChaCha20Poly1305(b_key)

    nonce = os.urandom(12)
    msg = b"hello over hybrid tunnel"
    ct_cipher = cipher_a.encrypt(nonce, msg, None)
    back = cipher_b.decrypt(nonce, ct_cipher, None)
    assert back == msg


# ---- Projekt-Keys im Handshake ----

def test_project_keys_hybrid_handshake():
    """peer1/peer2 Projektkeys funktionieren im Hybrid-Handshake."""
    # peer1 als Client, peer2 als Peer
    p1_ed = Ed25519PrivateKey.from_private_bytes(
        (KEYS_DIR / "peer1_ed25519").read_bytes()
    )
    p1_x = X25519PrivateKey.from_private_bytes(
        (KEYS_DIR / "peer1_x25519").read_bytes()
    )
    p2_x_pub = (KEYS_DIR / "peer2_x25519.pub").read_bytes()
    p2_mlkem_pub = (KEYS_DIR / "peer2_mlkem.pub").read_bytes()
    p2_mlkem_priv = (KEYS_DIR / "peer2_mlkem").read_bytes()

    # Client-Seite (peer1 als Client)
    p1_x_pub = _raw_pub(p1_x)
    with oqs.KeyEncapsulation("ML-KEM-1024") as enc:
        mlkem_ct, p1_mlkem_shared = enc.encap_secret(p2_mlkem_pub)

    # Peer-Seite (peer2 als Peer)
    p2_x = X25519PrivateKey.from_private_bytes(
        (KEYS_DIR / "peer2_x25519").read_bytes()
    )
    with oqs.KeyEncapsulation("ML-KEM-1024", p2_mlkem_priv) as dec:
        p2_mlkem_shared = dec.decap_secret(mlkem_ct)

    p1_x_shared = p1_x.exchange(X25519PublicKey.from_public_bytes(p2_x_pub))
    p2_x_shared = p2_x.exchange(X25519PublicKey.from_public_bytes(p1_x_pub))

    assert p1_x_shared == p2_x_shared
    assert p1_mlkem_shared == p2_mlkem_shared

    key1 = _derive_key_pq(p1_x_shared, p1_mlkem_shared)
    key2 = _derive_key_pq(p2_x_shared, p2_mlkem_shared)
    assert key1 == key2
