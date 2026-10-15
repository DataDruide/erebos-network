"""Reputation-System für Erebos Network.

Peers bewerten sich gegenseitig, dezentral.
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Rating:
    """Eine einzelne Bewertung."""

    rater_id: str  # Wer hat bewertet
    target_id: str  # Wen wurde bewertet
    score: float  # 0.0 - 1.0
    comment: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class Reputation:
    """Reputation eines Peers."""

    peer_id: str
    score: float = 0.5  # Startwert
    total_ratings: int = 0
    positive_ratings: int = 0
    negative_ratings: int = 0
    last_updated: float = field(default_factory=time.time)

    @property
    def positive_ratio(self) -> float:
        """Anteil positiver Bewertungen."""
        if self.total_ratings == 0:
            return 0.5
        return self.positive_ratings / self.total_ratings

    @property
    def age_seconds(self) -> float:
        """Alter der Reputation."""
        return time.time() - self.last_updated


class ReputationSystem:
    """Dezentrales Reputation-System.

    Peers sammeln Reputation durch:
    - Zuverlässigkeit
    - Ehrlichkeit
    - Positive Bewertungen
    """

    def __init__(
        self,
        decay_rate: float = 0.01,
        min_score: float = 0.0,
        max_score: float = 1.0,
    ):
        self.decay_rate = decay_rate
        self.min_score = min_score
        self.max_score = max_score
        self._reputations: dict[str, Reputation] = {}
        self._ratings: list[Rating] = []

    def list_all(self) -> list[Reputation]:
        """Gibt alle Reputation-Objekte zurueck (sortiert nach Score)."""
        reps = list(self._reputations.values())
        reps.sort(key=lambda r: r.score, reverse=True)
        return reps

    def get_reputation(self, peer_id: str) -> Reputation:
        """Gibt Reputation zurück (erstellt falls nicht vorhanden)."""
        if peer_id not in self._reputations:
            self._reputations[peer_id] = Reputation(peer_id=peer_id)
        return self._reputations[peer_id]

    def rate(
        self,
        rater_id: str,
        target_id: str,
        score: float,
        comment: str = "",
    ) -> Rating:
        """Bewertet einen Peer.

        Args:
            rater_id: Wer bewertet
            target_id: Wen bewertet
            score: 0.0 - 1.0
            comment: Optionaler Kommentar

        Returns:
            Rating

        Raises:
            ValueError: Wenn Score ungültig
        """
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"Score muss zwischen 0 und 1 liegen: {score}")

        rating = Rating(
            rater_id=rater_id,
            target_id=target_id,
            score=score,
            comment=comment,
        )
        self._ratings.append(rating)

        rep = self.get_reputation(target_id)
        rep.total_ratings += 1
        if score >= 0.5:
            rep.positive_ratings += 1
        else:
            rep.negative_ratings += 1

        # Gewichteter Durchschnitt
        alpha = 0.3  # Lernrate
        rep.score = alpha * score + (1 - alpha) * rep.score
        rep.score = max(self.min_score, min(self.max_score, rep.score))
        rep.last_updated = time.time()

        return rating

    def apply_decay(self, elapsed_seconds: float) -> int:
        """Wendet Reputation-Decay an.

        Args:
            elapsed_seconds: Vergangene Zeit

        Returns:
            Anzahl aktualisierter Reputationen
        """
        count = 0
        decay = self.decay_rate * (elapsed_seconds / 3600)
        for rep in self._reputations.values():
            rep.score = max(self.min_score, rep.score - decay)
            count += 1
        return count

    def is_trusted(self, peer_id: str, threshold: float = 0.7) -> bool:
        """Prüft, ob ein Peer vertrauenswürdig ist."""
        rep = self.get_reputation(peer_id)
        return rep.score >= threshold and rep.total_ratings >= 3

    @property
    def peer_count(self) -> int:
        """Anzahl bewerteter Peers."""
        return len(self._reputations)

    @property
    def total_ratings(self) -> int:
        """Gesamtzahl Bewertungen."""
        return len(self._ratings)

    def get_stats(self) -> dict:
        """Statistiken."""
        if not self._reputations:
            return {
                "peers": 0,
                "ratings": 0,
                "avg_score": 0.0,
            }

        scores = [r.score for r in self._reputations.values()]
        return {
            "peers": self.peer_count,
            "ratings": self.total_ratings,
            "avg_score": round(sum(scores) / len(scores), 3),
            "max_score": round(max(scores), 3),
            "min_score": round(min(scores), 3),
        }
