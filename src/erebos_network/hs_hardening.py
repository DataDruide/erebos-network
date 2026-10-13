"""HS-Descriptor-Hardening fuer Erebos Network.

Schuetzt gegen Descriptor-Flood-Angriffe (Tor 2026).
"""

import hashlib
import logging
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class HSHardeningConfig:
    """Konfiguration fuer HS-Descriptor-Hardening."""

    max_descriptor_size: int = 65536  # 64 KB
    max_descriptors_per_service: int = 10
    max_descriptors_total: int = 10000
    rate_limit_per_minute: int = 5
    pow_difficulty: int = 3  # 3 fuehrende Nullen
    descriptor_ttl_seconds: int = 3600
    cleanup_interval_seconds: int = 60


@dataclass
class HSDescriptorEntry:
    """Ein HS-Descriptor mit Metadaten."""

    service_id: str
    descriptor_id: str
    data: bytes
    pow_nonce: int
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = 3600
    access_count: int = 0

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds


class HSDescriptorHardening:
    """Descriptor-Hardening fuer Hidden Services.

    Schuetzt gegen:
    - Descriptor-Flood (Tor-Angriff 2026)
    - Memory-Erschoepfung
    - Sybil-Descriptors
    """

    def __init__(self, config: Optional[HSHardeningConfig] = None):
        self.config = config or HSHardeningConfig()
        self._descriptors: dict[str, HSDescriptorEntry] = {}
        self._service_counts: dict[str, int] = defaultdict(int)
        self._service_memory: dict[str, int] = defaultdict(int)
        self._rate_limits: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()
        self.stats = {
            "descriptors_accepted": 0,
            "rejected_size": 0,
            "rejected_per_service": 0,
            "rejected_total": 0,
            "rejected_rate_limit": 0,
            "rejected_pow": 0,
            "descriptors_expired": 0,
        }

    @staticmethod
    def compute_pow(service_id: str, descriptor_id: str, difficulty: int) -> tuple[str, int]:
        """Berechnet Proof-of-Work fuer einen Descriptor.

        Returns:
            (pow_hash, nonce)
        """
        target = "0" * difficulty
        nonce = 0
        while nonce < 10_000_000:
            candidate = f"{service_id}:{descriptor_id}:{nonce}"
            h = hashlib.sha256(candidate.encode()).hexdigest()
            if h.startswith(target):
                return h, nonce
            nonce += 1
        raise RuntimeError("PoW fehlgeschlagen")

    @staticmethod
    def verify_pow(
        service_id: str,
        descriptor_id: str,
        nonce: int,
        difficulty: int,
        expected_hash: str,
    ) -> bool:
        """Verifiziert Proof-of-Work."""
        candidate = f"{service_id}:{descriptor_id}:{nonce}"
        h = hashlib.sha256(candidate.encode()).hexdigest()
        if h != expected_hash:
            return False
        return h.startswith("0" * difficulty)

    def _check_rate_limit(self, service_id: str) -> bool:
        """Prueft Rate-Limit."""
        now = time.time()
        cutoff = now - 60.0
        self._rate_limits[service_id] = [
            t for t in self._rate_limits[service_id] if t > cutoff
        ]
        if (
            len(self._rate_limits[service_id])
            >= self.config.rate_limit_per_minute
        ):
            self.stats["rejected_rate_limit"] += 1
            return False
        self._rate_limits[service_id].append(now)
        return True

    def publish(
        self,
        service_id: str,
        descriptor_id: str,
        data: bytes,
        pow_hash: str,
        pow_nonce: int,
    ) -> bool:
        """Publiziert einen Descriptor mit allen Checks.

        Returns:
            True wenn akzeptiert
        """
        # 1. Groesse
        if len(data) > self.config.max_descriptor_size:
            self.stats["rejected_size"] += 1
            logger.warning(f"Descriptor zu gross: {len(data)}")
            return False

        # 2. Rate-Limit
        if not self._check_rate_limit(service_id):
            logger.warning(f"Rate-Limit fuer Service {service_id}")
            return False

        # 3. PoW
        if not self.verify_pow(
            service_id,
            descriptor_id,
            pow_nonce,
            self.config.pow_difficulty,
            pow_hash,
        ):
            self.stats["rejected_pow"] += 1
            logger.warning(f"Ungueltiger PoW fuer {descriptor_id}")
            return False

        # 4. Pro-Service-Limit
        if (
            self._service_counts[service_id]
            >= self.config.max_descriptors_per_service
        ):
            self.stats["rejected_per_service"] += 1
            logger.warning(f"Service {service_id} hat zu viele Descriptors")
            return False

        # 5. Global-Limit
        if len(self._descriptors) >= self.config.max_descriptors_total:
            self.stats["rejected_total"] += 1
            logger.warning("Maximale Descriptor-Anzahl erreicht")
            return False

        # 6. Akzeptieren
        entry = HSDescriptorEntry(
            service_id=service_id,
            descriptor_id=descriptor_id,
            data=data,
            pow_nonce=pow_nonce,
            ttl_seconds=self.config.descriptor_ttl_seconds,
        )
        self._descriptors[descriptor_id] = entry
        self._service_counts[service_id] += 1
        self._service_memory[service_id] += len(data)
        self.stats["descriptors_accepted"] += 1
        return True

    def get(self, descriptor_id: str) -> Optional[HSDescriptorEntry]:
        """Holt einen Descriptor (mit TTL-Check)."""
        entry = self._descriptors.get(descriptor_id)
        if not entry:
            return None
        if entry.is_expired:
            self._remove(descriptor_id)
            return None
        entry.access_count += 1
        return entry

    def _remove(self, descriptor_id: str) -> None:
        """Entfernt einen Descriptor."""
        entry = self._descriptors.pop(descriptor_id, None)
        if entry:
            self._service_counts[entry.service_id] -= 1
            self._service_memory[entry.service_id] -= entry.size
            if self._service_counts[entry.service_id] <= 0:
                del self._service_counts[entry.service_id]
                del self._service_memory[entry.service_id]

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
            self._remove(did)
            self.stats["descriptors_expired"] += 1

        self._last_cleanup = now
        return len(expired)

    @property
    def total_descriptors(self) -> int:
        return len(self._descriptors)

    @property
    def total_memory(self) -> int:
        return sum(self._service_memory.values())

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "total_descriptors": self.total_descriptors,
            "total_memory_bytes": self.total_memory,
            "active_services": len(self._service_counts),
            "config": {
                "max_size": self.config.max_descriptor_size,
                "max_per_service": self.config.max_descriptors_per_service,
                "max_total": self.config.max_descriptors_total,
                "pow_difficulty": self.config.pow_difficulty,
                "rate_limit": self.config.rate_limit_per_minute,
            },
        }
