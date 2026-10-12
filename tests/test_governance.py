"""Tests für Governance."""

import pytest

from erebos_network.consensus import VoteType
from erebos_network.governance import Governance, GovernanceConfig


def test_governance_init():
    """Governance initialisiert."""
    g = Governance()
    assert g.peer_count == 0


def test_register_peer():
    """Peer wird mit PoW registriert."""
    config = GovernanceConfig(pow_difficulty=2)
    g = Governance(config)
    result = g.register_peer("127.0.0.1:8000")
    assert result.peer_id.startswith("00")
    assert g.peer_count == 1
    assert g.is_registered(result.peer_id) is True


def test_register_peer_high_difficulty():
    """Peer mit höherer Difficulty."""
    config = GovernanceConfig(pow_difficulty=3)
    g = Governance(config)
    result = g.register_peer("127.0.0.1:9000")
    assert result.peer_id.startswith("000")


def test_can_vote_initial():
    """Neuer Peer kann nicht sofort abstimmen."""
    config = GovernanceConfig(pow_difficulty=2, min_reputation_to_vote=0.6)
    g = Governance(config)
    result = g.register_peer("127.0.0.1:8000")
    assert g.can_vote(result.peer_id) is False


def test_can_vote_after_ratings():
    """Nach positiven Bewertungen kann Peer abstimmen."""
    config = GovernanceConfig(pow_difficulty=2, min_reputation_to_vote=0.6)
    g = Governance(config)
    result = g.register_peer("127.0.0.1:8000")

    # Positive Bewertungen hinzufügen
    for i in range(5):
        g.reputation.rate(f"rater{i}", result.peer_id, 1.0)

    assert g.can_vote(result.peer_id) is True


def test_governance_propose_and_vote():
    """Governance erlaubt Vorschlag und Abstimmung."""
    config = GovernanceConfig(pow_difficulty=2, min_reputation_to_vote=0.3)
    g = Governance(config)

    # Peer 1 mit Reputation
    p1 = g.register_peer("127.0.0.1:8000")
    for i in range(5):
        g.reputation.rate(f"r{i}", p1.peer_id, 1.0)

    # Peer 2 mit Reputation
    p2 = g.register_peer("127.0.0.1:8001")
    for i in range(5):
        g.reputation.rate(f"r{i}", p2.peer_id, 1.0)

    # Vorschlag und Abstimmung
    g.propose("p1", "Erhöhe max_peers", "max_peers", "2000", p1.peer_id)
    g.vote("p1", p2.peer_id, VoteType.YES)

    result = g.get_result("p1")
    assert result["yes"] == 1
    assert result["total_votes"] == 1


def test_governance_stats():
    """Statistiken funktionieren."""
    config = GovernanceConfig(pow_difficulty=2)
    g = Governance(config)
    g.register_peer("127.0.0.1:8000")
    stats = g.get_stats()
    assert stats["peers"] == 1
    assert stats["pow_difficulty"] == 2
