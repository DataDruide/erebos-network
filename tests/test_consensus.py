"""Tests für Konsens-System."""

import pytest

from erebos_network.consensus import (
    ConsensusSystem,
    Proposal,
    VoteType,
)


def test_propose():
    """Vorschlag wird erstellt."""
    cs = ConsensusSystem()
    p = cs.propose(
        proposal_id="p1",
        title="Test Proposal",
        description="Test",
        parameter="max_peers",
        new_value="2000",
        proposer_id="peer1",
    )
    assert p.proposal_id == "p1"
    assert p.is_open is True
    assert cs.proposal_count == 1


def test_vote_yes():
    """Ja-Stimme wird gezählt."""
    cs = ConsensusSystem()
    cs.propose("p1", "Test", "Test", "param", "value", "peer1")
    cs.vote("p1", "peer2", VoteType.YES)
    result = cs.get_result("p1", total_peers=10)
    assert result["yes"] == 1
    assert result["total_votes"] == 1


def test_vote_multiple():
    """Mehrere Stimmen werden gezählt."""
    cs = ConsensusSystem()
    cs.propose("p1", "Test", "Test", "param", "value", "peer1")
    cs.vote("p1", "peer2", VoteType.YES)
    cs.vote("p1", "peer3", VoteType.YES)
    cs.vote("p1", "peer4", VoteType.NO)
    result = cs.get_result("p1", total_peers=10)
    assert result["yes"] == 2
    assert result["no"] == 1
    assert result["total_votes"] == 3


def test_double_vote_forbidden():
    """Doppelte Stimme wirft Fehler."""
    cs = ConsensusSystem()
    cs.propose("p1", "Test", "Test", "param", "value", "peer1")
    cs.vote("p1", "peer2", VoteType.YES)
    with pytest.raises(ValueError):
        cs.vote("p1", "peer2", VoteType.NO)


def test_unknown_proposal():
    """Unbekannter Vorschlag wirft Fehler."""
    cs = ConsensusSystem()
    with pytest.raises(ValueError):
        cs.vote("unknown", "peer1", VoteType.YES)


def test_approval():
    """Vorschlag wird angenommen."""
    cs = ConsensusSystem(quorum=0.5, approval_threshold=0.66)
    cs.propose("p1", "Test", "Test", "param", "value", "peer1")
    for i in range(7):
        cs.vote("p1", f"peer{i}", VoteType.YES)
    for i in range(3):
        cs.vote("p1", f"peer{i+10}", VoteType.NO)
    result = cs.get_result("p1", total_peers=10)
    assert result["has_quorum"] is True
    assert result["approval_ratio"] == 0.7
    assert result["is_approved"] is True


def test_no_quorum():
    """Ohne Quorum abgelehnt."""
    cs = ConsensusSystem(quorum=0.5)
    cs.propose("p1", "Test", "Test", "param", "value", "peer1")
    cs.vote("p1", "peer2", VoteType.YES)
    result = cs.get_result("p1", total_peers=100)
    assert result["has_quorum"] is False
    assert result["is_approved"] is False
