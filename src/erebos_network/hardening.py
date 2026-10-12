"""Memory-Hardening fuer Erebos Network.

Schuetzt gegen DoS-Angriffe (Descriptor Flood, Memory Exhaustion).

Basiert auf Tor-Descriptor-Flood-Analyse (2026).
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class HardeningConfig:
    """Konfiguration fuer Memory-Hardening."""

    max_descriptor_size: int = 65536
    max_descriptors_per_peer: int = 100
    max_descriptors_total: int = 10000
    descriptor_ttl_seconds: int = 3600
    rate_limit_per_minute: int = 60
    max_peer_memory_bytes: int = 10 * 1024 * 1024
    cleanup_interval_seconds: int = 60


@dataclass
class Descriptor:
    """Ein Descriptor (z.B. Peer-Info, Route)."""

    peer_id: str
    data: bytes
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = 3600
    access_count: int = 0

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds


class MemoryHardening:
    """Memory-Hardening fuer Erebos.

    Schuetzt gegen:
    - Descriptor Flood (Tor-Angriff)
    - Memory Exhaustion
    - Rate-Limit-Verletzungen
    """

    def __init__(self, config: Optional[HardeningConfig] = None):
        self.config = config or HardeningConfig()
        self._descriptors: dict[str, Descriptor] = {}
        self._peer_descriptor_count: dict[str, int] = defaultdict(int)
        self._peer_memory: dict[str, int] = defaultdict(int)
        self._rate_limits: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()
        self.stats = {
            "descriptors_added": 0,
            "descriptors_rejected_size": 0,
            "descriptors_rejected_peer": 0,
            "descriptors_rejected_total": 0,
            "descriptors_expired": 0,
            "rate_limit_hits": 0,
        }

    def add_descriptor(
        self,
        peer_id: str,
        descriptor_id: str,
        data: bytes,
    ) -> bool:
        """Fuegt einen Descriptor hinzu (mit allen Checks).

        Returns:
            True wenn akzeptiert
        """
        if len(data) > self.config.max_descriptor_size:
            self.stats["descriptors_rejected_size"] += 1
            logger.warning(
                f"Descriptor zu gross: {len(data)} > "
                f"{self.config.max_descriptor_size}"
            )
            return False

        if (
            self._peer_descriptor_count[peer_id]
            >= self.config.max_descriptors_per_peer
        ):
            self.stats["descriptors_rejected_peer"] += 1
            logger.warning(f"Peer {peer_id} hat zu viele Descriptors")
            return False

        if len(self._descriptors) >= self.config.max_descriptors_total:
            self.stats["descriptors_rejected_total"] += 1
            logger.warning("Maximale Descriptor-Anzahl erreicht")
            return False

        new_memory = self._peer_memory[peer_id] + len(data)
        if new_memory > self.config.max_peer_memory_bytes:
            self.stats["descriptors_rejected_peer"] += 1
            logger.warning(f"Peer {peer_id} hat zu viel Memory")
            return False

        descriptor = Descriptor(
            peer_id=peer_id,
            data=data,
            ttl_seconds=self.config.descriptor_ttl_seconds,
        )
        self._descriptors[descriptor_id] = descriptor
        self._peer_descriptor_count[peer_id] += 1
        self._peer_memory[peer_id] = new_memory
        self.stats["descriptors_added"] += 1

        return True

    def get_descriptor(self, descriptor_id: str) -> Optional[Descriptor]:
        """Holt einen Descriptor."""
        d = self._descriptors.get(descriptor_id)
        if d is None:
            return None
        if d.is_expired:
            self._remove_descriptor(descriptor_id)
            return None
        d.access_count += 1
        return d

    def _remove_descriptor(self, descriptor_id: str) -> None:
        """Entfernt einen Descriptor."""
        d = self._descriptors.pop(descriptor_id, None)
        if d:
            self._peer_descriptor_count[d.peer_id] -= 1
            self._peer_memory[d.peer_id] -= len(d.data)

    def check_rate_limit(self, peer_id: str) -> bool:
        """Prueft das Rate-Limit fuer einen Peer."""
        now = time.time()
        cutoff = now - 60.0
        self._rate_limits[peer_id] = [
            t for t in self._rate_limits[peer_id] if t > cutoff
        ]
        if (
            len(self._rate_limits[peer_id])
            >= self.config.rate_limit_per_minute
        ):
            self.stats["rate_limit_hits"] += 1
            return False
        self._rate_limits[peer_id].append(now)
        return True

    def cleanup(self, force: bool = False) -> int:
        """Entfernt abgelaufene Descriptors."""
        now = time.time()
        if (
            not force
            and (now - self._last_cleanup)
            < self.config.cleanup_interval_seconds
        ):
            return 0

        expired = [
            did for did, d in self._descriptors.items() if d.is_expired
        ]
        for did in expired:
            self._remove_descriptor(did)
            self.stats["descriptors_expired"] += 1

        self._last_cleanup = now
        return len(expired)

    @property
    def total_descriptors(self) -> int:
        return len(self._descriptors)

    @property
    def total_memory(self) -> int:
        return sum(self._peer_memory.values())

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "total_descriptors": self.total_descriptors,
            "total_memory_bytes": self.total_memory,
            "unique_peers": len(self._peer_descriptor_count),
        }
