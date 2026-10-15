"""HS-Introduction-Point-Rotation gegen Intersection-Angriffe.

Basiert auf Tor v3 Onion Services + go-tor.
Schuetzt gegen Intersection-Angriffe (arXiv 2026).
"""

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class RotationReason(Enum):
    """Grund fuer eine Rotation."""

    SCHEDULED = "scheduled"
    HEALTH = "health"
    AGE = "age"
    USAGE = "usage"
    INTERSECTION = "intersection"
    MANUAL = "manual"


@dataclass
class RotationConfig:
    """Konfiguration fuer Intro-Point-Rotation.

    Standard: 18-24h Rotation (Tor-Standard).
    """

    min_rotation_seconds: int = 18 * 3600  # 18h
    max_rotation_seconds: int = 24 * 3600  # 24h
    max_consecutive_failures: int = 3
    max_age_seconds: int = 24 * 3600
    # Tor rend-spec-v3: INTRO_POINT_LIFETIME_INTRODUCTIONS
    max_introductions: int = 16384
    num_intro_points: int = 3
    intersection_threshold: int = 3  # gleicher Peer in 3 Sessions
    intersection_window: int = 10  # ueber 10 Sessions
    retry_base_seconds: float = 2.0
    retry_max_seconds: float = 30.0
    retry_max_attempts: int = 3


@dataclass
class IntroPoint:
    """Ein Introduction Point."""

    point_id: str
    address: str
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    introductions_handled: int = 0
    is_healthy: bool = True

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def success_rate(self) -> float:
        total = self.total_failures + self.total_successes
        if total == 0:
            return 1.0
        return self.total_successes / total


@dataclass
class SessionRecord:
    """Eine Session mit Intro-Points."""

    session_id: str
    intro_point_ids: list[str]
    timestamp: float = field(default_factory=time.time)


class IntroPointManager:
    """Verwaltet Introduction Points mit Rotation.

    - Proaktive Rotation: 18-24h (randomisiert)
    - Reaktive Rotation: >=3 Fehler
    - Age-Rotation: >24h
    - Intersection-Detection: gleicher Peer in N Sessions
    """

    def __init__(self, config: Optional[RotationConfig] = None):
        self.config = config or RotationConfig()
        self._points: dict[str, IntroPoint] = {}
        self._sessions: list[SessionRecord] = []
        self._last_rotation: float = time.time()
        self._next_rotation: float = self._schedule_next_rotation()
        self.stats = {
            "points_created": 0,
            "points_rotated": 0,
            "rotations_scheduled": 0,
            "rotations_health": 0,
            "rotations_age": 0,
            "rotations_usage": 0,
            "rotations_intersection": 0,
            "intersections_detected": 0,
        }

    def _schedule_next_rotation(self) -> float:
        """Plant die naechste Rotation (randomisiert)."""
        min_s = self.config.min_rotation_seconds
        max_s = self.config.max_rotation_seconds

        if max_s <= min_s:
            interval = min_s
        else:
            interval = secrets.randbelow(max_s - min_s) + min_s

        return time.time() + interval

    def create_intro_point(self) -> IntroPoint:
        """Erstellt einen neuen Introduction Point."""
        point_id = hashlib.sha256(
            secrets.token_bytes(32)
        ).hexdigest()[:16]
        point = IntroPoint(
            point_id=point_id,
            address=f"intro-{point_id}.erebos",
        )
        self._points[point_id] = point
        self.stats["points_created"] += 1
        return point

    def ensure_intro_points(self) -> list[IntroPoint]:
        """Stellt sicher, dass genug Intro-Points existieren."""
        healthy = [p for p in self._points.values() if p.is_healthy]
        while len(healthy) < self.config.num_intro_points:
            new_point = self.create_intro_point()
            healthy.append(new_point)
        return healthy

    def record_success(self, point_id: str) -> None:
        """Zeichnet einen Erfolg auf."""
        point = self._points.get(point_id)
        if point:
            point.total_successes += 1
            point.consecutive_failures = 0
            point.last_seen = time.time()
            point.is_healthy = True

    def record_introduction(self, point_id: str) -> None:
        """Zählt eine erhaltene Introduction (INTRODUCE2-Zelle)."""
        point = self._points.get(point_id)
        if point:
            point.introductions_handled += 1

    def record_failure(self, point_id: str) -> Optional[RotationReason]:
        """Zeichnet einen Fehler auf.

        Returns:
            RotationReason wenn rotiert werden muss, sonst None
        """
        point = self._points.get(point_id)
        if not point:
            return None

        point.consecutive_failures += 1
        point.total_failures += 1
        point.last_seen = time.time()

        if point.consecutive_failures >= self.config.max_consecutive_failures:
            point.is_healthy = False
            logger.warning(
                f"Intro-Point {point_id} unhealthy "
                f"({point.consecutive_failures} Fehler)"
            )
            return RotationReason.HEALTH

        return None

    def rotate(
        self,
        point_id: str,
        reason: RotationReason,
    ) -> IntroPoint:
        """Rotiert einen Introduction Point."""
        old = self._points.pop(point_id, None)
        if old:
            logger.info(f"Intro-Point {point_id} rotiert: {reason.value}")
            self.stats["points_rotated"] += 1
            if reason == RotationReason.HEALTH:
                self.stats["rotations_health"] += 1
            elif reason == RotationReason.AGE:
                self.stats["rotations_age"] += 1
            elif reason == RotationReason.USAGE:
                self.stats["rotations_usage"] += 1
            elif reason == RotationReason.INTERSECTION:
                self.stats["rotations_intersection"] += 1
            elif reason == RotationReason.SCHEDULED:
                self.stats["rotations_scheduled"] += 1

        return self.create_intro_point()

    def check_rotation_needed(self) -> list[tuple[str, RotationReason]]:
        """Prueft, welche Intro-Points rotiert werden muessen."""
        to_rotate = []
        now = time.time()

        for point_id, point in self._points.items():
            if point.consecutive_failures >= self.config.max_consecutive_failures:
                to_rotate.append((point_id, RotationReason.HEALTH))
            elif point.age_seconds > self.config.max_age_seconds:
                to_rotate.append((point_id, RotationReason.AGE))
            elif point.introductions_handled >= self.config.max_introductions:
                to_rotate.append((point_id, RotationReason.USAGE))

        # Scheduled rotation
        if now >= self._next_rotation:
            for point_id in list(self._points.keys()):
                if (point_id, RotationReason.HEALTH) not in to_rotate:
                    to_rotate.append((point_id, RotationReason.SCHEDULED))
            self._next_rotation = self._schedule_next_rotation()

        return to_rotate

    def record_session(self, intro_point_ids: list[str]) -> None:
        """Zeichnet eine Session mit ihren Intro-Points auf."""
        session = SessionRecord(
            session_id=hashlib.sha256(
                f"{time.time()}:{secrets.token_hex(8)}".encode()
            ).hexdigest()[:16],
            intro_point_ids=list(intro_point_ids),
        )
        self._sessions.append(session)
        if len(self._sessions) > self.config.intersection_window * 2:
            self._sessions.pop(0)

    def detect_intersection(self) -> list[str]:
        """Erkennt Intersection (gleicher Peer in N Sessions).

        Returns:
            Liste von point_ids, die rotiert werden sollten
        """
        window = self._sessions[-self.config.intersection_window:]
        if len(window) < self.config.intersection_threshold:
            return []

        # Zaehle, wie oft jeder Point in den letzten Sessions auftaucht
        counts: dict[str, int] = {}
        for session in window:
            for pid in session.intro_point_ids:
                counts[pid] = counts.get(pid, 0) + 1

        # Points, die zu oft auftauchen
        suspicious = [
            pid for pid, count in counts.items()
            if count >= self.config.intersection_threshold
        ]

        if suspicious:
            self.stats["intersections_detected"] += 1
            logger.warning(
                f"Intersection erkannt: {suspicious} "
                f"(in {len(window)} Sessions)"
            )

        return suspicious

    def retry_backoff(self, attempt: int) -> float:
        """Berechnet Exponential Backoff fuer Retries.

        Args:
            attempt: Versuch-Nummer (0-basiert)

        Returns:
            Wartezeit in Sekunden
        """
        delay = self.config.retry_base_seconds * (2 ** attempt)
        return min(delay, self.config.retry_max_seconds)

    @property
    def point_count(self) -> int:
        return len(self._points)

    @property
    def healthy_count(self) -> int:
        return sum(1 for p in self._points.values() if p.is_healthy)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "point_count": self.point_count,
            "healthy_count": self.healthy_count,
            "session_count": len(self._sessions),
            "seconds_until_next_rotation": max(
                0, int(self._next_rotation - time.time())
            ),
            "config": {
                "min_rotation_hours": self.config.min_rotation_seconds / 3600,
                "max_rotation_hours": self.config.max_rotation_seconds / 3600,
                "max_failures": self.config.max_consecutive_failures,
                "max_introductions": self.config.max_introductions,
                "intersection_threshold": self.config.intersection_threshold,
            },
        }
