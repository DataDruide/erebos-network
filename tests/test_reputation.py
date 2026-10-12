"""Tests für Reputation-System."""

import pytest

from erebos_network.reputation import Rating, Reputation, ReputationSystem


def test_reputation_default():
    """Standard-Reputation ist 0.5."""
    rs = ReputationSystem()
    rep = rs.get_reputation("peer1")
    assert rep.score == 0.5
    assert rep.total_ratings == 0


def test_rate_positive():
    """Positive Bewertung erhöht Reputation."""
    rs = ReputationSystem()
    rs.rate("rater1", "target1", 1.0)
    rep = rs.get_reputation("target1")
    assert rep.total_ratings == 1
    assert rep.positive_ratings == 1
    assert rep.score > 0.5


def test_rate_negative():
    """Negative Bewertung senkt Reputation."""
    rs = ReputationSystem()
    rs.rate("rater1", "target1", 0.0)
    rep = rs.get_reputation("target1")
    assert rep.negative_ratings == 1
    assert rep.score < 0.5


def test_rate_invalid_score():
    """Ungültiger Score wirft Fehler."""
    rs = ReputationSystem()
    with pytest.raises(ValueError):
        rs.rate("rater1", "target1", 1.5)
    with pytest.raises(ValueError):
        rs.rate("rater1", "target1", -0.1)


def test_is_trusted():
    """Vertrauenswürdigkeit wird geprüft."""
    rs = ReputationSystem()
    for i in range(5):
        rs.rate(f"rater{i}", "target1", 1.0)
    assert rs.is_trusted("target1") is True


def test_is_not_trusted():
    """Nicht vertrauenswürdig bei wenig Ratings."""
    rs = ReputationSystem()
    rs.rate("rater1", "target1", 1.0)
    assert rs.is_trusted("target1") is False  # Nur 1 Rating


def test_decay():
    """Reputation-Decay funktioniert."""
    rs = ReputationSystem(decay_rate=0.1)
    rs.rate("rater1", "target1", 1.0)
    initial = rs.get_reputation("target1").score
    rs.apply_decay(3600)
    assert rs.get_reputation("target1").score < initial


def test_stats():
    """Statistiken funktionieren."""
    rs = ReputationSystem()
    rs.rate("rater1", "target1", 1.0)
    rs.rate("rater2", "target2", 0.8)
    stats = rs.get_stats()
    assert stats["peers"] == 2
    assert stats["ratings"] == 2
    assert 0.5 < stats["avg_score"] < 1.0
