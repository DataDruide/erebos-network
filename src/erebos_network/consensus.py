"""Konsens-Protokoll für Erebos Network.

Dezentrale Abstimmung über Netzwerk-Parameter.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VoteType(Enum):
    """Typ einer Abstimmung."""

    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"


@dataclass
class Proposal:
    """Ein Vorschlag zur Abstimmung."""

    proposal_id: str
    title: str
    description: str
    parameter: str  # Welcher Parameter geändert werden soll
    new_value: str  # Neuer Wert
    proposer_id: str
    created_at: float = field(default_factory=time.time)
    deadline: float = 0.0  # Unix-Timestamp
    votes: dict[str, VoteType] = field(default_factory=dict)

    def __post_init__(self):
        if self.deadline == 0.0:
            self.deadline = self.created_at + 86400  # 24h

    @property
    def is_open(self) -> bool:
        """Ob Abstimmung noch offen ist."""
        return time.time() < self.deadline

    @property
    def yes_votes(self) -> int:
        return sum(1 for v in self.votes.values() if v == VoteType.YES)

    @property
    def no_votes(self) -> int:
        return sum(1 for v in self.votes.values() if v == VoteType.NO)

    @property
    def abstain_votes(self) -> int:
        return sum(1 for v in self.votes.values() if v == VoteType.ABSTAIN)

    @property
    def total_votes(self) -> int:
        return len(self.votes)

    @property
    def approval_ratio(self) -> float:
        """Anteil Ja-Stimmen an allen Stimmen."""
        if self.total_votes == 0:
            return 0.0
        return self.yes_votes / self.total_votes


class ConsensusSystem:
    """Dezentrales Konsens-System.

    Peers stimmen über Netzwerk-Parameter ab.
    """

    def __init__(
        self,
        quorum: float = 0.5,
        approval_threshold: float = 0.66,
    ):
        self.quorum = quorum
        self.approval_threshold = approval_threshold
        self._proposals: dict[str, Proposal] = {}
        self._votes_cast: dict[str, set[str]] = {}  # proposal -> peer_ids

    def propose(
        self,
        proposal_id: str,
        title: str,
        description: str,
        parameter: str,
        new_value: str,
        proposer_id: str,
        duration_seconds: int = 86400,
    ) -> Proposal:
        """Erstellt einen Vorschlag."""
        proposal = Proposal(
            proposal_id=proposal_id,
            title=title,
            description=description,
            parameter=parameter,
            new_value=new_value,
            proposer_id=proposer_id,
            deadline=time.time() + duration_seconds,
        )
        self._proposals[proposal_id] = proposal
        self._votes_cast[proposal_id] = set()
        return proposal

    def vote(
        self,
        proposal_id: str,
        peer_id: str,
        vote_type: VoteType,
    ) -> bool:
        """Stimmt über einen Vorschlag ab.

        Returns:
            True wenn Stimme akzeptiert

        Raises:
            ValueError: Wenn Vorschlag nicht existiert oder geschlossen
        """
        if proposal_id not in self._proposals:
            raise ValueError(f"Vorschlag nicht gefunden: {proposal_id}")

        proposal = self._proposals[proposal_id]

        if not proposal.is_open:
            raise ValueError("Abstimmung ist geschlossen")

        if peer_id in self._votes_cast[proposal_id]:
            raise ValueError(f"Peer {peer_id} hat bereits abgestimmt")

        proposal.votes[peer_id] = vote_type
        self._votes_cast[proposal_id].add(peer_id)
        return True

    def get_result(self, proposal_id: str, total_peers: int) -> dict:
        """Gibt Abstimmungsergebnis zurück.

        Args:
            proposal_id: Vorschlag
            total_peers: Gesamtzahl der Peers im Netzwerk

        Returns:
            Ergebnis-Dict
        """
        if proposal_id not in self._proposals:
            raise ValueError(f"Vorschlag nicht gefunden: {proposal_id}")

        proposal = self._proposals[proposal_id]
        participation = proposal.total_votes / max(total_peers, 1)
        has_quorum = participation >= self.quorum
        is_approved = (
            has_quorum
            and proposal.approval_ratio >= self.approval_threshold
        )

        return {
            "proposal_id": proposal_id,
            "title": proposal.title,
            "yes": proposal.yes_votes,
            "no": proposal.no_votes,
            "abstain": proposal.abstain_votes,
            "total_votes": proposal.total_votes,
            "participation": round(participation, 3),
            "approval_ratio": round(proposal.approval_ratio, 3),
            "has_quorum": has_quorum,
            "is_approved": is_approved,
            "is_open": proposal.is_open,
        }

    @property
    def proposal_count(self) -> int:
        return len(self._proposals)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            "proposals": self.proposal_count,
            "open_proposals": sum(
                1 for p in self._proposals.values() if p.is_open
            ),
        }
