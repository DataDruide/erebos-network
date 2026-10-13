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
