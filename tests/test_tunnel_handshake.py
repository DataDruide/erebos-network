"""Tests fuer den X25519+Ed25519-Handshake (tunnel.py).

Nachbau der Handshake-Sequenz ohne echte Sockets: alle Schritte
laufen ueber eine asyncio-Pipe.
"""

import asyncio
import os

import pytest

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

from erebos_network.tunnel import (
    KEYS_DIR,
    _derive_key,
    _load_or_create_keypair,
    _send_frame,
    _recv_frame,
)


def _raw_priv(key):
    return key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _raw_pub(key):
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


class FakeWriter:
    """StreamWriter-Ersatz, schreibt in einen StreamReader."""
    def __init__(self, reader):
        self.reader = reader
    def write(self, data):
        self.reader.feed_data(data)
    async def drain(self):
        pass


# ---- Signatur / Verifikation ----

def test_ed25519_sign_verify():
    """Ed25519 Signatur erzeugen und verifizieren."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    msg = b"some x25519 pubkey bytes"
    sig = priv.sign(msg)
    assert len(sig) == 64

    pub.verify(sig, msg)  # wirft keine Exception


def test_ed25519_wrong_key_fails():
    """Signatur mit falschem Pubkey schlaegt fehl."""
    priv_a = Ed25519PrivateKey.generate()
    priv_b = Ed25519PrivateKey.generate()

    msg = b"payload"
    sig = priv_a.sign(msg)
    with pytest.raises(Exception):
        priv_b.public_key().verify(sig, msg)


def test_ed25519_tampered_message_fails():
    """Manipulierte Message schlaegt Verifikation fehl."""
    priv = Ed25519PrivateKey.generate()
    sig = priv.sign(b"original")
    with pytest.raises(Exception):
        priv.public_key().verify(sig, b"tampered")


# ---- X25519 Exchange ----

def test_x25519_exchange_symmetric():
    """Beide Seiten berechnen dasselbe Shared Secret."""
    a_priv = X25519PrivateKey.generate()
    b_priv = X25519PrivateKey.generate()

    a_shared = a_priv.exchange(b_priv.public_key())
    b_shared = b_priv.exchange(a_priv.public_key())
    assert a_shared == b_shared


def test_x25519_shared_length():
    """X25519 Shared Secret ist 32 Byte."""
    a = X25519PrivateKey.generate()
    b = X25519PrivateKey.generate()
    shared = a.exchange(b.public_key())
    assert len(shared) == 32


# ---- HKDF ueber Shared Secret ----

def test_derive_key_from_x25519():
    """HKDF ueber X25519-Shared-Secret liefert 32 Byte, symmetrisch."""
    a_priv = X25519PrivateKey.generate()
    b_priv = X25519PrivateKey.generate()

    shared_a = a_priv.exchange(b_priv.public_key())
    shared_b = b_priv.exchange(a_priv.public_key())

    key_a = _derive_key(shared_a)
    key_b = _derive_key(shared_b)
    assert key_a == key_b
    assert len(key_a) == 32


# ---- Vollstaendige Handshake-Sequenz ----

@pytest.mark.asyncio
async def test_full_handshake_sequence():
    """Vollstaendige X25519+Ed25519-Sequenz ueber asyncio-Pipe."""
    # Client-Seite
    client_ed = Ed25519PrivateKey.generate()
    client_x = X25519PrivateKey.generate()
    client_x_pub = _raw_pub(client_x)

    # Peer-Seite
    peer_ed = Ed25519PrivateKey.generate()
    peer_x = X25519PrivateKey.generate()
    peer_x_pub = _raw_pub(peer_x)

    reader = asyncio.StreamReader()
    writer = FakeWriter(reader)

    # 1. Client sendet x_pub + sig
    client_sig = client_ed.sign(client_x_pub)
    await _send_frame(writer, client_x_pub + client_sig)

    # 2. Peer liest, verifiziert
    received = await _recv_frame(reader)
    assert received == client_x_pub + client_sig
    rx_x_pub = received[:32]
    rx_sig = received[32:]
    client_ed.public_key().verify(rx_sig, rx_x_pub)
    assert rx_x_pub == client_x_pub

    # 3. Peer sendet eigene x_pub + sig zurueck (ueber neue Pipe)
    reader2 = asyncio.StreamReader()
    writer2 = FakeWriter(reader2)
    peer_sig = peer_ed.sign(peer_x_pub)
    await _send_frame(writer2, peer_x_pub + peer_sig)

    # 4. Client liest, verifiziert
    received2 = await _recv_frame(reader2)
    rx_peer_x_pub = received2[:32]
    rx_peer_sig = received2[32:]
    peer_ed.public_key().verify(rx_peer_sig, rx_peer_x_pub)
    assert rx_peer_x_pub == peer_x_pub

    # 5. Beide berechnen Shared Secret -> gleicher Key
    client_shared = client_x.exchange(X25519PublicKey.from_public_bytes(rx_peer_x_pub))
    peer_shared = peer_x.exchange(X25519PublicKey.from_public_bytes(rx_x_pub))

    key_client = _derive_key(client_shared)
    key_peer = _derive_key(peer_shared)
    assert key_client == key_peer


# ---- ChaCha20Poly1305 ueber den abgeleiteten Key ----

def test_chacha_roundtrip_with_derived_key():
    """ChaCha20-Poly1305 mit HKDF-abgeleitetem Key."""
    a_priv = X25519PrivateKey.generate()
    b_priv = X25519PrivateKey.generate()
    shared = a_priv.exchange(b_priv.public_key())
    key = _derive_key(shared)

    cipher = ChaCha20Poly1305(key)
    nonce = os.urandom(12)
    plaintext = b"hello over the tunnel"

    ct = cipher.encrypt(nonce, plaintext, None)
    back = cipher.decrypt(nonce, ct, None)
    assert back == plaintext


def test_chacha_wrong_key_fails():
    """ChaCha20-Poly1305 mit falschem Key schlaegt fehl."""
    key1 = os.urandom(32)
    key2 = os.urandom(32)

    cipher1 = ChaCha20Poly1305(key1)
    cipher2 = ChaCha20Poly1305(key2)

    nonce = os.urandom(12)
    ct = cipher1.encrypt(nonce, b"message", None)
    with pytest.raises(Exception):
        cipher2.decrypt(nonce, ct, None)


# ---- Integration mit den echten Projekt-Keys ----

def test_project_keys_handshake_works():
    """Die echten peer1/peer2 Keys aus KEYS_DIR funktionieren im Handshake."""
    c_ed_priv, c_x_priv, c_ed_pub, c_x_pub = _load_or_create_keypair("peer1")
    p_ed_priv, p_x_priv, p_ed_pub, p_x_pub = _load_or_create_keypair("peer2")

    # Signatur
    sig = c_ed_priv.sign(c_x_pub)
    p_ed = Ed25519PublicKey.from_public_bytes(c_ed_pub)
    p_ed.verify(sig, c_x_pub)

    # Shared Secret
    shared_c = c_x_priv.exchange(X25519PublicKey.from_public_bytes(p_x_pub))
    shared_p = p_x_priv.exchange(X25519PublicKey.from_public_bytes(c_x_pub))
    assert shared_c == shared_p
    assert len(_derive_key(shared_c)) == 32
