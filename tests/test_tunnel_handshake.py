"""Tests fuer den Hybrid-Handshake (X25519 + ML-KEM-1024) im Tunnel.

Nachbau der Handshake-Sequenz ohne echte Sockets. Prueft:
- Frame-Layout (version || x_pub || mlkem_pub || sig)
- Peer-Antwort (version || x_pub || mlkem_ct || sig)
- Signaturdeckung ueber version || x_pub || mlkem_*
- Session-Key-Symmetrie zwischen beiden Seiten
- ChaCha20-Poly1305 ueber den abgeleiteten Key
"""

import asyncio
import os

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

from erebos_network.tunnel import (
    HANDSHAKE_V1_CLASSIC,
    HANDSHAKE_V2_HYBRID,
    X25519_PUB_LEN,
    MLKEM_PUB_LEN,
    MLKEM_CT_LEN,
    ED25519_SIG_LEN,
    MLKEM_ALG,
    _derive_key,
    _derive_key_pq,
    _send_frame,
    _recv_frame,
)


def _raw_pub(key):
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


class FakeWriter:
    def __init__(self, reader):
        self.reader = reader
    def write(self, data):
        self.reader.feed_data(data)
    async def drain(self):
        pass


# ---- Konstanten ----

def test_handshake_version_constants():
    """V1_CLASSIC und V2_HYBRID sind unterscheidbar."""
    assert HANDSHAKE_V1_CLASSIC == 0x01
    assert HANDSHAKE_V2_HYBRID == 0x02


def test_length_constants():
    """Wire-Format-Laengen stimmen mit liboqs ueberein."""
    assert X25519_PUB_LEN == 32
    assert MLKEM_PUB_LEN == 1568
    assert MLKEM_CT_LEN == 1568
    assert ED25519_SIG_LEN == 64


# ---- Frame-Layout ----

def test_client_handshake_frame_size():
    """Client-Frame: version(1) + x_pub(32) + mlkem_pub(1568) + sig(64)."""
    ed = Ed25519PrivateKey.generate()
    x = X25519PrivateKey.generate()
    with oqs.KeyEncapsulation(MLKEM_ALG) as kem:
        mlkem_pub = kem.generate_keypair()

    x_pub = _raw_pub(x)
    signed_data = bytes([HANDSHAKE_V2_HYBRID]) + x_pub + mlkem_pub
    sig = ed.sign(signed_data)

    frame = bytes([HANDSHAKE_V2_HYBRID]) + x_pub + mlkem_pub + sig
    expected_size = 1 + 32 + 1568 + 64
    assert len(frame) == expected_size
    assert expected_size == 1665


def test_peer_response_frame_size():
    """Peer-Frame: version(1) + x_pub(32) + mlkem_ct(1568) + sig(64)."""
    ed = Ed25519PrivateKey.generate()
    x = X25519PrivateKey.generate()
    with oqs.KeyEncapsulation(MLKEM_ALG) as kem:
        mlkem_pub = kem.generate_keypair()
    with oqs.KeyEncapsulation(MLKEM_ALG) as enc:
        mlkem_ct, _ = enc.encap_secret(mlkem_pub)

    x_pub = _raw_pub(x)
    signed_data = bytes([HANDSHAKE_V2_HYBRID]) + x_pub + mlkem_ct
    sig = ed.sign(signed_data)

    frame = bytes([HANDSHAKE_V2_HYBRID]) + x_pub + mlkem_ct + sig
    assert len(frame) == 1665


# ---- Signaturen ----

def test_signature_covers_version_x_and_mlkem():
    """Signatur deckt version || x_pub || mlkem_pub."""
    ed = Ed25519PrivateKey.generate()
    x = X25519PrivateKey.generate()
    with oqs.KeyEncapsulation(MLKEM_ALG) as kem:
        mlkem_pub = kem.generate_keypair()

    x_pub = _raw_pub(x)
    signed = bytes([HANDSHAKE_V2_HYBRID]) + x_pub + mlkem_pub
    sig = ed.sign(signed)

    # Korrekte Verifikation
    ed.public_key().verify(sig, signed)

    # Manipulierte version schlaegt fehl
    with pytest.raises(Exception):
        ed.public_key().verify(
            sig, bytes([HANDSHAKE_V1_CLASSIC]) + x_pub + mlkem_pub
        )

    # Manipulierter mlkem_pub schlaegt fehl
    with pytest.raises(Exception):
        ed.public_key().verify(
            sig,
            bytes([HANDSHAKE_V2_HYBRID]) + x_pub + b"\x00" * MLKEM_PUB_LEN,
        )


def test_peer_signature_covers_version_x_and_ct():
    """Peer-Signatur deckt version || x_pub || mlkem_ct."""
    ed = Ed25519PrivateKey.generate()
    x = X25519PrivateKey.generate()
    with oqs.KeyEncapsulation(MLKEM_ALG) as kem:
        mlkem_pub = kem.generate_keypair()
    with oqs.KeyEncapsulation(MLKEM_ALG) as enc:
        mlkem_ct, _ = enc.encap_secret(mlkem_pub)

    x_pub = _raw_pub(x)
    signed = bytes([HANDSHAKE_V2_HYBRID]) + x_pub + mlkem_ct
    sig = ed.sign(signed)
    ed.public_key().verify(sig, signed)


# ---- Vollstaendige Sequenz ----

@pytest.mark.asyncio
async def test_full_hybrid_handshake_sequence():
    """Client sendet Frame, Peer antwortet, beide berechnen denselben Key."""
    # --- Peer-Identitaet ---
    peer_ed = Ed25519PrivateKey.generate()
    peer_x = X25519PrivateKey.generate()
    with oqs.KeyEncapsulation(MLKEM_ALG) as kem:
        peer_mlkem_pub = kem.generate_keypair()
        peer_mlkem_priv = kem.export_secret_key()

    peer_x_pub = _raw_pub(peer_x)
    peer_ed_pub = peer_ed.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    # --- Client-Identitaet ---
    client_ed = Ed25519PrivateKey.generate()
    client_x = X25519PrivateKey.generate()
    with oqs.KeyEncapsulation(MLKEM_ALG) as kem:
        client_mlkem_pub = kem.generate_keypair()
        client_mlkem_priv = kem.export_secret_key()

    client_x_pub = _raw_pub(client_x)

    # === Runde 1: Client sendet ===
    reader = asyncio.StreamReader()
    writer = FakeWriter(reader)

    signed = bytes([HANDSHAKE_V2_HYBRID]) + client_x_pub + client_mlkem_pub
    sig = client_ed.sign(signed)
    frame = bytes([HANDSHAKE_V2_HYBRID]) + client_x_pub + client_mlkem_pub + sig
    await _send_frame(writer, frame)

    # === Peer empfaengt und verifiziert ===
    received = await _recv_frame(reader)
    assert received == frame
    assert received[0] == HANDSHAKE_V2_HYBRID
    rx_client_x_pub = received[1:1 + X25519_PUB_LEN]
    rx_client_mlkem_pub = received[
        1 + X25519_PUB_LEN : 1 + X25519_PUB_LEN + MLKEM_PUB_LEN
    ]
    rx_sig = received[1 + X25519_PUB_LEN + MLKEM_PUB_LEN:]
    client_ed.public_key().verify(
        rx_sig,
        bytes([HANDSHAKE_V2_HYBRID]) + rx_client_x_pub + rx_client_mlkem_pub,
    )

    # === Peer: X25519 + ML-KEM Encapsulate ===
    x_shared_peer = peer_x.exchange(
        X25519PublicKey.from_public_bytes(rx_client_x_pub)
    )
    with oqs.KeyEncapsulation(MLKEM_ALG) as enc:
        mlkem_ct, mlkem_shared_peer = enc.encap_secret(rx_client_mlkem_pub)

    # === Peer sendet Antwort ===
    reader2 = asyncio.StreamReader()
    writer2 = FakeWriter(reader2)

    peer_signed = bytes([HANDSHAKE_V2_HYBRID]) + peer_x_pub + mlkem_ct
    peer_sig = peer_ed.sign(peer_signed)
    response = (
        bytes([HANDSHAKE_V2_HYBRID]) + peer_x_pub + mlkem_ct + peer_sig
    )
    await _send_frame(writer2, response)

    # === Client empfaengt ===
    rx_response = await _recv_frame(reader2)
    assert rx_response == response
    rx_peer_x_pub = rx_response[1:1 + X25519_PUB_LEN]
    rx_mlkem_ct = rx_response[
        1 + X25519_PUB_LEN : 1 + X25519_PUB_LEN + MLKEM_CT_LEN
    ]
    rx_peer_sig = rx_response[1 + X25519_PUB_LEN + MLKEM_CT_LEN:]
    peer_ed.public_key().verify(
        rx_peer_sig,
        bytes([HANDSHAKE_V2_HYBRID]) + rx_peer_x_pub + rx_mlkem_ct,
    )

    # === Client: X25519 + ML-KEM Decapsulate ===
    x_shared_client = client_x.exchange(
        X25519PublicKey.from_public_bytes(rx_peer_x_pub)
    )
    with oqs.KeyEncapsulation(MLKEM_ALG, client_mlkem_priv) as dec:
        mlkem_shared_client = dec.decap_secret(rx_mlkem_ct)

    # === Symmetrie ===
    assert x_shared_client == x_shared_peer
    assert mlkem_shared_client == mlkem_shared_peer

    key_client = _derive_key_pq(x_shared_client, mlkem_shared_client)
    key_peer = _derive_key_pq(x_shared_peer, mlkem_shared_peer)
    assert key_client == key_peer


# ---- ChaCha mit abgeleitetem Key ----

def test_chacha_with_hybrid_key():
    """ChaCha20-Poly1305 mit hybrid abgeleitetem Key."""
    x_shared = os.urandom(32)
    mlkem_shared = os.urandom(32)
    key = _derive_key_pq(x_shared, mlkem_shared)

    cipher = ChaCha20Poly1305(key)
    nonce = os.urandom(12)
    plaintext = b"hello over the hybrid tunnel"
    ct = cipher.encrypt(nonce, plaintext, None)
    back = cipher.decrypt(nonce, ct, None)
    assert back == plaintext


# ---- Klassischer Pfad bleibt verfuegbar ----

def test_classic_derive_key_still_works():
    """_derive_key (klassisch) bleibt nutzbar fuer Rueckwaertskompatibilitaet."""
    shared = os.urandom(32)
    key = _derive_key(shared)
    assert len(key) == 32


def test_classic_and_pq_derive_differ():
    """Klassischer und PQ-Pfad liefern unterschiedliche Keys bei gleichem Input."""
    shared = os.urandom(32)
    mlkem_shared = os.urandom(32)
    k_classic = _derive_key(shared)
    k_pq = _derive_key_pq(shared, mlkem_shared)
    assert k_classic != k_pq
