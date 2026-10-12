"""Governance-Modul für Erebos Network.

Kombiniert PoW, Reputation und Konsens.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from .consensus import ConsensusSystem, VoteType
from .pow import PoWConfig, ProofOfWork, compute_pow, verify_pow
from .reputation import ReputationSystem


@dataclass
class GovernanceConfig:
    """Konfiguration für Governance."""

    pow_difficulty: int = 4
    quorum: float = 0.5
    approval_threshold: float = 0.66
    min_reputation_to_vote: float = 0.3


class Governance:
    """Dezentrale Governance.

    Kombiniert:
    - Proof-of-Work (Sybil-Schutz)
    - Reputation (Vertrauen)
    - Konsens (Abstimmung)
    """

    def __init__(self, config: Optional[GovernanceConfig] = None):
        self.config = config or GovernanceConfig()
        self.pow_config = PoWConfig(difficulty=self.config.pow_difficulty)
        self.reputation = ReputationSystem()
        self.consensus = ConsensusSystem(
            quorum=self.config.quorum,
            approval_threshold=self.config.approval_threshold,
        )
        self._registered_peers: dict[str, ProofOfWork] = {}

    def register_peer(self, address: str) -> ProofOfWork:
        """Registriert einen Peer mit Proof-of-Work.

        Args:
            address: IP:Port

        Returns:
            ProofOfWork
        """
        pow_result = compute_pow(
            seed=address,
            difficulty=self.config.pow_difficulty,
        )
        self._registered_peers[pow_result.peer_id] = pow_result

        # Initial-Reputation
        self.reputation.get_reputation(pow_result.peer_id)

        return pow_result

    def is_registered(self, peer_id: str) -> bool:
        """Prüft, ob ein Peer registriert ist."""
        return peer_id in self._registered_peers

    def can_vote(self, peer_id: str) -> bool:
        """Prüft, ob ein Peer abstimmen darf."""
        if not self.is_registered(peer_id):
            return False
        rep = self.reputation.get_reputation(peer_id)
        return rep.score >= self.config.min_reputation_to_vote

    def propose(
        self,
        proposal_id: str,
        title: str,
        parameter: str,
        new_value: str,
        proposer_id: str,
    ):
        """Erstellt einen Vorschlag."""
        if not self.can_vote(proposer_id):
            raise ValueError(
                f"Peer {proposer_id[:16]} darf nicht vorschlagen"
            )
        return self.consensus.propose(
            proposal_id=proposal_id,
            title=title,
            description=f"Änderung von {parameter} auf {new_value}",
            parameter=parameter,
            new_value=new_value,
            proposer_id=proposer_id,
        )

    def vote(
        self,
        proposal_id: str,
        peer_id: str,
        vote_type: VoteType,
    ) -> bool:
        """Stimmt ab."""
        if not self.can_vote(peer_id):
            raise ValueError(
                f"Peer {peer_id[:16]} darf nicht abstimmen"
            )
        return self.consensus.vote(proposal_id, peer_id, vote_type)

    def get_result(self, proposal_id: str) -> dict:
        """Gibt Abstimmungsergebnis zurück."""
        return self.consensus.get_result(
            proposal_id,
            total_peers=len(self._registered_peers),
        )

    @property
    def peer_count(self) -> int:
        return len(self._registered_peers)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            "peers": self.peer_count,
            "pow_difficulty": self.config.pow_difficulty,
            "reputation": self.reputation.get_stats(),
            "consensus": self.consensus.get_stats(),
        }
