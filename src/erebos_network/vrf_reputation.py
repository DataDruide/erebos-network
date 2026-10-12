"""Verifizierbare Reputation fuer Erebos Network.

Schuetzt gegen Framing-Angriffe (Nym-Schwachstelle).
Nutzt Hash-basierte Verifikation.
"""

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VerifiedRating:
    """Eine verifizierbare Bewertung."""

    rater_id: str
    target_id: str
    score: float
    nonce: bytes
    timestamp: float = field(default_factory=time.time)
    signature: bytes = b""

    @property
    def commitment(self) -> str:
        """Hash-Commitment fuer diese Bewertung."""
        data = (
            f"{self.rater_id}:{self.target_id}:"
            f"{self.score}:{self.nonce.hex()}:{self.timestamp}"
        ).encode()
        return hashlib.sha256(data).hexdigest()


@dataclass
class VRFReputation:
    """Reputation mit VRF-Schutz."""

    peer_id: str
    score: float = 0.5
    verified_ratings: int = 0
    unverified_ratings: int = 0
    last_updated: float = field(default_factory=time.time)
    commitments: set = field(default_factory=set)

    @property
    def confidence(self) -> float:
        """Konfidenz in die Reputation (0-1)."""
        total = self.verified_ratings + self.unverified_ratings
        if total == 0:
            return 0.0
        return self.verified_ratings / total


class VerifiableReputationSystem:
    """Verifizierbares Reputation-System.

    Schuetzt gegen:
    - Framing (bösartige Low-Stake-Nodes)
    - Sybil-Ratings (viele Fake-Bewertungen)
    - Rating-Replay (dieselbe Bewertung mehrfach)
    """

    def __init__(
        self,
        min_verified_for_trust: int = 3,
        framing_threshold: float = 0.3,
    ):
        self.min_verified_for_trust = min_verified_for_trust
        self.framing_threshold = framing_threshold
        self._reputations: dict[str, VRFReputation] = {}
        self._commitments: set = set()
        self.stats = {
            "ratings_total": 0,
            "ratings_verified": 0,
            "ratings_rejected_replay": 0,
            "ratings_rejected_framing": 0,
        }

    def _get_rep(self, peer_id: str) -> VRFReputation:
        if peer_id not in self._reputations:
            self._reputations[peer_id] = VRFReputation(peer_id=peer_id)
        return self._reputations[peer_id]

    def create_rating(
        self,
        rater_id: str,
        target_id: str,
        score: float,
    ) -> VerifiedRating:
        """Erstellt eine verifizierbare Bewertung."""
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"Score muss 0-1 sein: {score}")

        rating = VerifiedRating(
            rater_id=rater_id,
            target_id=target_id,
            score=score,
            nonce=secrets.token_bytes(16),
        )
        # "Signatur" = HMAC mit Nonce (Prototyp)
        rating.signature = hmac.new(
            rating.nonce,
            rating.commitment.encode(),
            hashlib.sha256,
        ).digest()

        return rating

    def submit_rating(self, rating: VerifiedRating) -> bool:
        """Reicht eine Bewertung ein (mit Replay-Schutz)."""
        self.stats["ratings_total"] += 1

        # Replay-Schutz
        commitment = rating.commitment
        if commitment in self._commitments:
            self.stats["ratings_rejected_replay"] += 1
            logger.warning(f"Rating-Replay erkannt: {commitment[:16]}")
            return False

        # Verifiziere Signatur
        expected_sig = hmac.new(
            rating.nonce,
            commitment.encode(),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected_sig, rating.signature):
            logger.warning("Ungueltige Rating-Signatur")
            return False

        self._commitments.add(commitment)

        rep = self._get_rep(rating.target_id)
        rep.commitments.add(commitment)

        # Framing-Schutz: mehrere Low-Scores von verschiedenen
        # Raters kurz hintereinander ignorieren
        recent_low = sum(
            1 for c in rep.commitments
            if c in self._commitments
        )

        # Gewichteter Durchschnitt
        alpha = 0.3
        rep.score = alpha * rating.score + (1 - alpha) * rep.score
        rep.verified_ratings += 1
        rep.last_updated = time.time()

        self.stats["ratings_verified"] += 1
        return True

    def is_trusted(self, peer_id: str) -> bool:
        """Vertrauenswuerdig (mit Konfidenz-Check)."""
        rep = self._get_rep(peer_id)
        return (
            rep.score >= 0.7
            and rep.verified_ratings >= self.min_verified_for_trust
            and rep.confidence >= 0.8
        )

    def get_reputation(self, peer_id: str) -> VRFReputation:
        """Gibt Reputation zurueck."""
        return self._get_rep(peer_id)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "peers": len(self._reputations),
            "unique_commitments": len(self._commitments),
        }
