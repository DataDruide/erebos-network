"""Dynamic PoW gegen IoT-Sybil-Angriffe.

Schuetzt gegen Botnetze (Kimwolf 2026).
Difficulty skaliert mit Netzwerkgroesse und Angriffs-Mustern.
"""

import hashlib
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DynamicPoWConfig:
    """Konfiguration fuer Dynamic PoW."""

    base_difficulty: int = 3  # Fuehrende Nullen
    min_difficulty: int = 2
    max_difficulty: int = 8
    scale_per_1000_peers: float = 0.5
    attack_multiplier: float = 2.0
    attack_window_seconds: int = 60
    attack_threshold_per_minute: int = 100
    reputation_bypass_threshold: float = 0.8
    reputation_difficulty_reduction: int = 1
    max_new_peers_per_ip_per_hour: int = 5
    max_new_peers_per_subnet_per_hour: int = 20


@dataclass
class PeerAttempt:
    """Ein Peer-Registrierungs-Versuch."""

    address: str
    ip: str
    timestamp: float = field(default_factory=time.time)
    difficulty: int = 0
    success: bool = False


class IPRateLimiter:
    """IP-basiertes Rate-Limiting fuer neue Peers."""

    def __init__(self, config: Optional[DynamicPoWConfig] = None):
        self.config = config or DynamicPoWConfig()
        self._ip_attempts: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        self._subnet_attempts: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=5000)
        )
        self.stats = {
            "attempts_total": 0,
            "rejected_ip": 0,
            "rejected_subnet": 0,
        }

    @staticmethod
    def _extract_ip(address: str) -> str:
        """Extrahiert IP aus IP:Port."""
        if address.startswith("["):
            return address.split("]")[0][1:]
        return address.rsplit(":", 1)[0]

    @staticmethod
    def _extract_subnet(ip: str) -> str:
        """Extrahiert /24-Subnetz."""
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3]) + ".0/24"
        return ip

    def _cleanup(self, dq: deque, window: float) -> None:
        """Entfernt alte Eintraege."""
        cutoff = time.time() - window
        while dq and dq[0] < cutoff:
            dq.popleft()

    def allow(self, address: str) -> bool:
        """Prueft, ob eine Registrierung erlaubt ist."""
        self.stats["attempts_total"] += 1
        ip = self._extract_ip(address)
        subnet = self._extract_subnet(ip)
        window = 3600  # 1 Stunde

        # IP-Check
        self._cleanup(self._ip_attempts[ip], window)
        if len(self._ip_attempts[ip]) >= self.config.max_new_peers_per_ip_per_hour:
            self.stats["rejected_ip"] += 1
            logger.warning(f"IP-Rate-Limit: {ip}")
            return False

        # Subnetz-Check
        self._cleanup(self._subnet_attempts[subnet], window)
        if (
            len(self._subnet_attempts[subnet])
            >= self.config.max_new_peers_per_subnet_per_hour
        ):
            self.stats["rejected_subnet"] += 1
            logger.warning(f"Subnetz-Rate-Limit: {subnet}")
            return False

        # Akzeptieren
        now = time.time()
        self._ip_attempts[ip].append(now)
        self._subnet_attempts[subnet].append(now)
        return True

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "active_ips": len(self._ip_attempts),
            "active_subnets": len(self._subnet_attempts),
        }


class DynamicPoW:
    """Dynamic Proof-of-Work.

    Difficulty skaliert mit:
    - Netzwerkgroesse
    - Angriffs-Mustern (ploetzliche Anstiege)
    - Reputation (Vertrauens-Bypass)
    """

    def __init__(self, config: Optional[DynamicPoWConfig] = None):
        self.config = config or DynamicPoWConfig()
        self._peer_count: int = 0
        self._recent_attempts: deque = deque(maxlen=10000)
        self._current_difficulty: int = config.base_difficulty if config else 3
        self.rate_limiter = IPRateLimiter(self.config)
        self.stats = {
            "pow_computed": 0,
            "pow_verified": 0,
            "pow_rejected": 0,
            "attacks_detected": 0,
            "difficulty_increases": 0,
            "difficulty_decreases": 0,
        }

    def update_peer_count(self, count: int) -> None:
        """Aktualisiert die Netzwerkgroesse."""
        self._peer_count = count

    def _detect_attack(self) -> bool:
        """Erkennt ploetzliche Anstiege (Botnet-Angriff)."""
        now = time.time()
        cutoff = now - self.config.attack_window_seconds

        recent = [a for a in self._recent_attempts if a.timestamp > cutoff]
        rate_per_minute = len(recent) * (60.0 / self.config.attack_window_seconds)

        if rate_per_minute >= self.config.attack_threshold_per_minute:
            self.stats["attacks_detected"] += 1
            logger.warning(
                f"Angriff erkannt: {rate_per_minute:.1f} Versuche/Minute"
            )
            return True
        return False

    def compute_difficulty(
        self, reputation: float = 0.5
    ) -> int:
        """Berechnet die aktuelle Difficulty.

        Args:
            reputation: Peer-Reputation (0-1)

        Returns:
            Difficulty (Anzahl fuehrende Nullen)
        """
        # Basis
        diff = float(self.config.base_difficulty)

        # Netzwerkgroesse
        diff += (self._peer_count / 1000.0) * self.config.scale_per_1000_peers

        # Angriffs-Muster
        if self._detect_attack():
            diff *= self.config.attack_multiplier

        # Reputation-Bypass
        if reputation >= self.config.reputation_bypass_threshold:
            diff -= self.config.reputation_difficulty_reduction

        # Grenzen
        diff = max(self.config.min_difficulty, diff)
        diff = min(self.config.max_difficulty, diff)

        new_diff = int(round(diff))

        # Stats
        if new_diff > self._current_difficulty:
            self.stats["difficulty_increases"] += 1
        elif new_diff < self._current_difficulty:
            self.stats["difficulty_decreases"] += 1

        self._current_difficulty = new_diff
        return new_diff

    @staticmethod
    def compute_pow(
        seed: str,
        difficulty: int,
        max_attempts: int = 10_000_000,
    ) -> tuple[str, int]:
        """Berechnet PoW.

        Returns:
            (hash, nonce)
        """
        target = "0" * difficulty
        nonce = 0
        while nonce < max_attempts:
            candidate = f"{seed}:{nonce}"
            h = hashlib.sha256(candidate.encode()).hexdigest()
            if h.startswith(target):
                return h, nonce
            nonce += 1
        raise RuntimeError(f"PoW fehlgeschlagen (difficulty={difficulty})")

    @staticmethod
    def verify_pow(
        seed: str,
        nonce: int,
        difficulty: int,
        expected_hash: str,
    ) -> bool:
        """Verifiziert PoW."""
        candidate = f"{seed}:{nonce}"
        h = hashlib.sha256(candidate.encode()).hexdigest()
        if h != expected_hash:
            return False
        return h.startswith("0" * difficulty)

    def register_peer(
        self,
        address: str,
        reputation: float = 0.5,
    ) -> dict:
        """Registriert einen Peer mit Dynamic PoW.

        Returns:
            Dict mit status + details
        """
        # IP-Rate-Limit
        if not self.rate_limiter.allow(address):
            return {
                "status": "rejected",
                "reason": "rate_limit",
                "difficulty": self._current_difficulty,
            }

        # Difficulty
        difficulty = self.compute_difficulty(reputation)

        # PoW berechnen (Client-Seite simuliert)
        seed = hashlib.sha256(
            f"{address}:{time.time()}".encode()
        ).hexdigest()[:16]

        try:
            pow_hash, nonce = self.compute_pow(seed, difficulty)
        except RuntimeError:
            return {
                "status": "rejected",
                "reason": "pow_failed",
                "difficulty": difficulty,
            }

        attempt = PeerAttempt(
            address=address,
            ip=self.rate_limiter._extract_ip(address),
            difficulty=difficulty,
            success=True,
        )
        self._recent_attempts.append(attempt)
        self.stats["pow_computed"] += 1

        return {
            "status": "accepted",
            "difficulty": difficulty,
            "nonce": nonce,
            "pow_hash": pow_hash,
            "seed": seed,
        }

    def verify_peer(
        self,
        address: str,
        seed: str,
        nonce: int,
        pow_hash: str,
        difficulty: int,
    ) -> bool:
        """Verifiziert einen Peer-Registrierungs-Versuch."""
        if not self.verify_pow(seed, nonce, difficulty, pow_hash):
            self.stats["pow_rejected"] += 1
            return False
        self.stats["pow_verified"] += 1
        return True

    @property
    def current_difficulty(self) -> int:
        return self._current_difficulty

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "current_difficulty": self._current_difficulty,
            "peer_count": self._peer_count,
            "rate_limiter": self.rate_limiter.get_stats(),
            "config": {
                "base_difficulty": self.config.base_difficulty,
                "max_difficulty": self.config.max_difficulty,
                "attack_multiplier": self.config.attack_multiplier,
            },
        }
