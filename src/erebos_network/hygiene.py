"""Client-seitige Hygiene fuer Erebos Network.

Schuetzt gegen den Server (Destination), der Anfragen
zeitlich korrelieren koennte.

Basiert auf Nym "Layer 2" Empfehlungen.
"""

import asyncio
import hashlib
import logging
import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class HygieneConfig:
    """Konfiguration fuer Client-seitige Hygiene."""

    min_delay_ms: int = 0
    max_delay_ms: int = 2000
    padding_enabled: bool = True
    padding_block_size: int = 1024
    min_request_interval_ms: int = 100
    max_requests_per_minute: int = 60
    burst_allowed: bool = False


@dataclass
class RequestMetadata:
    """Metadaten einer Anfrage."""

    request_id: str
    created_at: float = field(default_factory=time.time)
    scheduled_at: float = 0.0
    sent_at: float = 0.0
    jitter_ms: float = 0.0


class HygieneManager:
    """Client-seitige Hygiene.

    Schuetzt gegen Server, die Anfragen zeitlich korrelieren.
    """

    def __init__(self, config: Optional[HygieneConfig] = None):
        self.config = config or HygieneConfig()
        self._recent_requests: list[float] = []
        self.stats = {
            "requests_total": 0,
            "requests_delayed": 0,
            "requests_padded": 0,
            "total_jitter_ms": 0.0,
        }

    def randomize_timing(self) -> float:
        """Zieht eine zufaellige Verzoegerung in Sekunden."""
        delay_ms = random.uniform(
            self.config.min_delay_ms,
            self.config.max_delay_ms,
        )
        self.stats["total_jitter_ms"] += delay_ms
        if delay_ms > 0:
            self.stats["requests_delayed"] += 1
        return delay_ms / 1000.0

    async def schedule_request(self) -> RequestMetadata:
        """Plant eine Anfrage mit Jitter."""
        self.stats["requests_total"] += 1
        meta = RequestMetadata(
            request_id=hashlib.sha256(
                f"{time.time()}:{random.random()}".encode()
            ).hexdigest()[:16],
        )
        jitter = self.randomize_timing()
        meta.jitter_ms = jitter * 1000
        meta.scheduled_at = time.time() + jitter
        await asyncio.sleep(jitter)
        meta.sent_at = time.time()
        return meta

    def pad_request(self, data: bytes) -> bytes:
        """Polstert eine Anfrage auf Blockgroesse.

        Nutzt kryptographisch sichere Zufallsbytes als Padding
        (kein Laengen-Praefix wie bei PKCS#7).
        """
        if not self.config.padding_enabled:
            return data

        block = self.config.padding_block_size
        target = ((len(data) // block) + 1) * block
        padding_length = target - len(data)

        if padding_length == 0:
            return data

        padding = secrets.token_bytes(padding_length)
        self.stats["requests_padded"] += 1
        return data + padding

    def unpad_request(self, padded: bytes, original_length: int) -> bytes:
        """Entfernt Padding (benoetigt Original-Laenge)."""
        return padded[:original_length]

    def check_rate_limit(self) -> bool:
        """Prueft, ob das Rate-Limit eingehalten wird."""
        now = time.time()
        cutoff = now - 60.0
        self._recent_requests = [
            t for t in self._recent_requests if t > cutoff
        ]
        if len(self._recent_requests) >= self.config.max_requests_per_minute:
            return False
        self._recent_requests.append(now)
        return True

    def get_stats(self) -> dict:
        """Statistiken."""
        avg_jitter = 0.0
        if self.stats["requests_total"] > 0:
            avg_jitter = (
                self.stats["total_jitter_ms"]
                / self.stats["requests_total"]
            )
        return {
            **self.stats,
            "avg_jitter_ms": round(avg_jitter, 2),
            "recent_requests": len(self._recent_requests),
        }
