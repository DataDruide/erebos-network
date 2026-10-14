"""Tests fuer authentifizierten Handshake."""

import time

import pytest

from erebos_network.auth_handshake import (
    AuthenticatedHandshake,
    HandshakeConfig,
    HandshakeMessage,
    HandshakeState,
)
from erebos_network.crypto.hybrid_kem import HybridKEM
from erebos_network.crypto.pq_sig import PostQuantumSignature


# --- HandshakeMessage ---

def test_message_to_bytes():
    """Nachricht serialisiert."""
    msg = HandshakeMessage(
        sender_id="alice",
        x25519_pub=b"x" * 32,
        mlkem_ct=b"k" * 1568,
    )
    data = msg.to_bytes()
    assert b"alice" in data


def test_message_signable():
    """Signierbare Bytes."""
    msg = HandshakeMessage(
        sender_id="alice",
        x25519_pub=b"x" * 32,
        mlkem_ct=b"k" * 1568,
    )
    signable = msg.signable_bytes()
    assert b"alice" in signable


# --- HandshakeConfig ---

def test_config_default():
    """Standard-Konfiguration."""
    c = HandshakeConfig()
    assert c.use_signatures is True
    assert c.use_mac is True
    assert c.session_binding is True


# --- AuthenticatedHandshake ---

def test_handshake_init():
    """Handshake initialisiert."""
    h = AuthenticatedHandshake()
    assert h.stats["handshakes_initiated"] == 0


def test_handshake_initiate():
    """Initiator startet Handshake."""
    h = AuthenticatedHandshake()
    kem = HybridKEM()
    sig = PostQuantumSignature()

    responder_pub = kem.generate_keypair()
    initiator_sig = sig.generate_keypair()
    responder_sig = sig.generate_keypair()

    msg, state = h.initiate(
        initiator_id="alice",
        responder_pubkey=responder_pub,
        responder_sigkey=responder_sig.public_key,
        initiator_sigkey=initiator_sig,
    )
    assert msg.sender_id == "alice"
    assert len(msg.signature) > 0
    assert h.stats["handshakes_initiated"] == 1


def test_handshake_timestamp_replay():
    """Alter Timestamp wird abgelehnt."""
    config = HandshakeConfig(max_timestamp_skew_seconds=1)
    h = AuthenticatedHandshake(config)
    kem = HybridKEM()
    sig = PostQuantumSignature()

    responder_pub = kem.generate_keypair()
    initiator_sig = sig.generate_keypair()
    responder_sig = sig.generate_keypair()

    msg, _ = h.initiate(
        "alice", responder_pub, responder_sig.public_key, initiator_sig
    )
    # Timestamp 1 Stunde zurueck
    msg.timestamp = time.time() - 3600

    with pytest.raises(ValueError, match="Timestamp"):
        h.respond(
            "bob",
            msg,
            initiator_sig.public_key,
            responder_pub,
            responder_sig,
        )


def test_handshake_invalid_signature():
    """Ungueltige Signatur wird abgelehnt."""
    h = AuthenticatedHandshake()
    kem = HybridKEM()
    sig = PostQuantumSignature()

    responder_pub = kem.generate_keypair()
    initiator_sig = sig.generate_keypair()
    responder_sig = sig.generate_keypair()
    wrong_sig = sig.generate_keypair()

    msg, _ = h.initiate(
        "alice", responder_pub, responder_sig.public_key, initiator_sig
    )
    # Signatur manipulieren
    msg.signature = b"invalid" * 100

    with pytest.raises(ValueError, match="Signatur"):
        h.respond(
            "bob",
            msg,
            initiator_sig.public_key,
            responder_pub,
            responder_sig,
        )


def test_handshake_stats():
    """Statistiken funktionieren."""
    h = AuthenticatedHandshake()
    stats = h.get_stats()
    assert "config" in stats
    assert stats["config"]["signatures"] is True
    assert stats["config"]["mac"] is True


def test_handshake_without_signatures():
    """Handshake ohne Signaturen."""
    config = HandshakeConfig(use_signatures=False, use_mac=False)
    h = AuthenticatedHandshake(config)
    stats = h.get_stats()
    assert stats["config"]["signatures"] is False
    assert stats["config"]["mac"] is False


def test_handshake_without_binding():
    """Handshake ohne Session-Bindung."""
    config = HandshakeConfig(session_binding=False)
    h = AuthenticatedHandshake(config)
    stats = h.get_stats()
    assert stats["config"]["session_binding"] is False


# ---------------------------------------------------------------------------
# Symmetrie: Initiator und Responder müssen denselben Session-Key berechnen
# ---------------------------------------------------------------------------

def test_session_key_is_symmetric():
    """Initiator und Responder berechnen denselben Session-Key.

    Kritisch: Der Radicle-Bug (2026) war, dass Handshake OK war,
    aber Session-Keys divergierten -> Klartext.
    """
    from erebos_network.crypto.pq_kem import PostQuantumKEM
    from erebos_network.crypto.pq_sig import PostQuantumSignature
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    kem = PostQuantumKEM()
    sig = PostQuantumSignature()

    # Responder-Identität
    x_priv = X25519PrivateKey.generate()
    x_pub = x_priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    mlkem_kp = kem.generate_keypair()

    from erebos_network.crypto.hybrid_kem import HybridKeyPair
    responder_pubkey = HybridKeyPair(
        x25519_private=b"",
        x25519_public=x_pub,
        mlkem_public=mlkem_kp.public_key,
        mlkem_private=mlkem_kp.private_key,
    )

    sig_kp = sig.generate_keypair()
    sig_kp2 = sig.generate_keypair()

    initiator = AuthenticatedHandshake()
    responder = AuthenticatedHandshake()

    # Initiator startet
    msg1, init_state = initiator.initiate(
        initiator_id="alice",
        responder_pubkey=responder_pubkey,
        responder_sigkey=sig_kp2.public_key,
        initiator_sigkey=sig_kp,
    )

    # Responder antwortet
    msg2, resp_state = responder.respond(
        responder_id="bob",
        initiator_msg=msg1,
        initiator_sigkey=sig_kp.public_key,
        responder_pubkey=responder_pubkey,
        responder_sigkey=sig_kp2,
    )

    # Initiator bestätigt
    initiator_session = initiator.confirm(
        initiator_state=init_state,
        responder_msg=msg2,
        responder_sigkey=sig_kp2.public_key,
        responder_pubkey=responder_pubkey,
    )

    # Symmetrie: beide Session-Keys müssen gleich sein
    assert initiator_session.session_key == resp_state["session_key"], (
        "Session-Keys divergieren! "
        f"initiator={initiator_session.session_key.hex()[:16]}... "
        f"responder={resp_state['session_key'].hex()[:16]}..."
    )


def test_session_key_uses_hkdf():
    """_derive_session_key nutzt HKDF (RFC 5869)."""
    from erebos_network.auth_handshake import AuthenticatedHandshake
    from erebos_network.crypto.hybrid_kem import derive_hybrid_key
    import os

    h = AuthenticatedHandshake()
    x_ss = os.urandom(32)
    pq_ss = os.urandom(32)

    # Direkter HKDF-Aufruf mit gleichem info
    expected = derive_hybrid_key(
        x_ss, pq_ss, info=b"erebos-auth-v1:alice:bob"
    )
    actual = h._derive_session_key(x_ss, pq_ss, "alice", "bob")
    assert actual == expected


def test_session_key_domain_separation():
    """Verschiedene IDs -> verschiedene Session-Keys."""
    from erebos_network.auth_handshake import AuthenticatedHandshake
    import os

    h = AuthenticatedHandshake()
    x_ss = os.urandom(32)
    pq_ss = os.urandom(32)

    k1 = h._derive_session_key(x_ss, pq_ss, "alice", "bob")
    k2 = h._derive_session_key(x_ss, pq_ss, "alice", "carol")
    k3 = h._derive_session_key(x_ss, pq_ss, "bob", "alice")  # Reihenfolge!
    assert k1 != k2
    assert k1 != k3
    assert k2 != k3
