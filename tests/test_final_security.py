"""Tests fuer E2E, VRF-Reputation, Hidden Services, Obfuskation."""

import pytest

from erebos_network.e2e import E2EState, EndToEnd
from erebos_network.vrf_reputation import (
    VerifiableReputationSystem,
    VerifiedRating,
)
from erebos_network.hidden_service import HiddenService, HSState
from erebos_network.obfuscation import (
    ApplicationObfuscation,
    ObfuscationConfig,
)


# --- E2E Tests ---

def test_e2e_create_session():
    """E2E-Session wird erstellt."""
    e2e = EndToEnd()
    session = e2e.create_session("alice", "bob")
    assert session.initiator_id == "alice"
    assert session.responder_id == "bob"
    assert session.state == E2EState.INITIATED


def test_e2e_establish():
    """E2E-Session wird etabliert."""
    e2e = EndToEnd()
    session = e2e.create_session("alice", "bob")
    assert e2e.establish(session.session_id) is True
    assert session.is_established is True


def test_e2e_send_receive():
    """E2E senden + empfangen funktioniert."""
    e2e = EndToEnd()
    session = e2e.create_session("alice", "bob")
    e2e.establish(session.session_id)

    payload = b"Hello, Erebos!"
    encrypted = e2e.send(session.session_id, payload)
    assert encrypted != payload

    decrypted = e2e.receive(session.session_id, encrypted)
    assert decrypted == payload


def test_e2e_not_established():
    """E2E ohne Establishment wirft Fehler."""
    e2e = EndToEnd()
    session = e2e.create_session("alice", "bob")
    with pytest.raises(ValueError):
        e2e.send(session.session_id, b"data")


def test_e2e_stats():
    """E2E-Statistiken."""
    e2e = EndToEnd()
    s = e2e.create_session("alice", "bob")
    e2e.establish(s.session_id)
    stats = e2e.get_stats()
    assert stats["sessions_created"] == 1
    assert stats["sessions_established"] == 1


# --- VRF-Reputation Tests ---

def test_vrf_create_rating():
    """VRF-Rating wird erstellt."""
    vrf = VerifiableReputationSystem()
    rating = vrf.create_rating("alice", "bob", 0.9)
    assert rating.rater_id == "alice"
    assert rating.score == 0.9
    assert len(rating.nonce) == 16


def test_vrf_submit_rating():
    """VRF-Rating wird eingereicht."""
    vrf = VerifiableReputationSystem()
    rating = vrf.create_rating("alice", "bob", 0.9)
    assert vrf.submit_rating(rating) is True
    rep = vrf.get_reputation("bob")
    assert rep.verified_ratings == 1


def test_vrf_replay_rejected():
    """VRF-Replay wird abgelehnt."""
    vrf = VerifiableReputationSystem()
    rating = vrf.create_rating("alice", "bob", 0.9)
    vrf.submit_rating(rating)
    assert vrf.submit_rating(rating) is False
    assert vrf.stats["ratings_rejected_replay"] == 1


def test_vrf_invalid_score():
    """VRF ungueltiger Score wirft Fehler."""
    vrf = VerifiableReputationSystem()
    with pytest.raises(ValueError):
        vrf.create_rating("alice", "bob", 1.5)


def test_vrf_trust():
    """VRF-Vertrauen nach mehreren Ratings."""
    vrf = VerifiableReputationSystem(min_verified_for_trust=3)
    for i in range(5):
        r = vrf.create_rating(f"rater{i}", "bob", 0.9)
        vrf.submit_rating(r)
    assert vrf.is_trusted("bob") is True


# --- Hidden Service Tests ---

def test_hs_create_service():
    """Hidden Service wird erstellt."""
    hs = HiddenService()
    service = hs.create_service()
    assert service.address.endswith(".erebos")
    assert hs.service_count == 1


def test_hs_lookup():
    """Hidden Service Lookup funktioniert."""
    hs = HiddenService()
    service = hs.create_service()
    found = hs.lookup(service.address)
    assert found is not None
    assert found.service_id == service.service_id


def test_hs_establish_session():
    """HS-Session wird etabliert."""
    hs = HiddenService()
    service = hs.create_service()
    session = hs.establish_session("client1", service.service_id)
    assert session is not None
    assert session.rendezvous_point
    assert hs.session_count == 1


def test_hs_send_receive():
    """HS senden + empfangen."""
    hs = HiddenService()
    service = hs.create_service()
    session = hs.establish_session("client1", service.service_id)

    assert hs.send(session.session_id, b"data") is True
    assert hs.receive(session.session_id, 4) is True

    stats = hs.get_stats()
    assert stats["bytes_transferred"] == 8


# --- Obfuscation Tests ---

def test_obfuscation_obfuscate():
    """Obfuskation veraendert Payload."""
    ob = ApplicationObfuscation()
    result = ob.obfuscate(b"hello")
    assert result != b"hello"
    assert len(result) > len(b"hello")


def test_obfuscation_size_noise():
    """Obfuskation Size-Noise funktioniert."""
    config = ObfuscationConfig(
        min_payload_size=1024,
        max_payload_size=1024,
        add_protocol_cover=False,
    )
    ob = ApplicationObfuscation(config)
    result = ob.obfuscate(b"hello")
    assert len(result) == 1024


def test_obfuscation_protocol_cover():
    """Obfuskation Protocol-Cover funktioniert."""
    ob = ApplicationObfuscation()
    result = ob.obfuscate(b"data")
    # HTTP/HTTPS/DNS/etc. sollte drin sein
    assert any(
        p in result
        for p in [b"HTTP/1.1", b"HTTPS", b"DNS", b"NTP", b"QUIC"]
    )


def test_obfuscation_timing_noise():
    """Obfuskation Timing-Noise funktioniert."""
    ob = ApplicationObfuscation()
    delay = ob.add_timing_noise()
    assert 0.0 <= delay <= 0.1


def test_obfuscation_cover_message():
    """Obfuskation Cover-Nachricht."""
    ob = ApplicationObfuscation()
    cover = ob.generate_cover_message()
    assert 256 <= len(cover) <= 1024


def test_obfuscation_stats():
    """Obfuskation Statistiken."""
    ob = ApplicationObfuscation()
    ob.obfuscate(b"data")
    stats = ob.get_stats()
    assert stats["messages_obfuscated"] == 1
