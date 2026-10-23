"""Tests fuer E2E, VRF-Reputation, Hidden Services, Obfuskation."""

import pytest

from erebos_network.vrf_reputation import (
    VerifiableReputationSystem,
    VerifiedRating,
)
from erebos_network.obfuscation import (
    ApplicationObfuscation,
    ObfuscationConfig,
)


# --- E2E Tests ---

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
