"""Mixnet-Layer für Erebos Network.

Kombiniert Padding, Delay, Batching und Cover-Traffic.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from .batching import Batch, Batcher
from .cover import CoverConfig, generate_cover_message, should_send_cover
from .delay import DelayConfig, apply_delay
from .padding import PaddedMessage, pad_message

logger = logging.getLogger(__name__)


@dataclass
class MixnetConfig:
    """Konfiguration für den Mixnet-Layer."""

    padding_enabled: bool = True
    padding_block_size: int = 1024
    delay_config: DelayConfig = field(default_factory=DelayConfig)
    batch_size: int = 10
    batch_timeout_ms: int = 1000
    cover_config: CoverConfig = field(default_factory=CoverConfig)


@dataclass
class MixnetStats:
    """Statistiken für den Mixnet-Layer."""

    messages_in: int = 0
    messages_out: int = 0
    cover_messages: int = 0
    total_delay_ms: float = 0.0
    total_padding_bytes: int = 0

    @property
    def avg_delay_ms(self) -> float:
        """Durchschnittliche Verzögerung."""
        if self.messages_out == 0:
            return 0.0
        return self.total_delay_ms / self.messages_out


class MixnetLayer:
    """Der Mixnet-Layer.

    Verarbeitet Nachrichten durch:
    1. Padding (Größe verstecken)
    2. Batching (Gruppieren)
    3. Delay (Timing verstecken)
    4. Cover (Dummy-Traffic)
    """

    def __init__(self, config: Optional[MixnetConfig] = None):
        self.config = config or MixnetConfig()
        self.batcher = Batcher(
            max_size=self.config.batch_size,
            max_wait_ms=self.config.batch_timeout_ms,
        )
        self.stats = MixnetStats()

    async def process(
        self, message: bytes, apply_padding: bool = True
    ) -> bytes:
        """Verarbeitet eine Nachricht durch den Mixnet-Layer.

        Args:
            message: Original-Nachricht
            apply_padding: Ob Padding angewendet werden soll

        Returns:
            Verarbeitete Nachricht
        """
        self.stats.messages_in += 1
        current = message

        if apply_padding and self.config.padding_enabled:
            padded = pad_message(
                current,
                block_size=self.config.padding_block_size,
            )
            self.stats.total_padding_bytes += padded.overhead
            current = padded.data

        if self.config.delay_config.max_ms > 0:
            delay = await apply_delay(self.config.delay_config)
            self.stats.total_delay_ms += delay * 1000

        self.stats.messages_out += 1
        return current

    async def process_batch(self, messages: list[bytes]) -> list[bytes]:
        """Verarbeitet mehrere Nachrichten.

        Args:
            messages: Liste von Nachrichten

        Returns:
            Liste von verarbeiteten Nachrichten
        """
        results = []
        for msg in messages:
            result = await self.process(msg)
            results.append(result)
        return results

    async def generate_cover_traffic(
        self, count: int = 1
    ) -> list[bytes]:
        """Erzeugt Cover-Traffic.

        Args:
            count: Anzahl Nachrichten

        Returns:
            Liste von Cover-Nachrichten
        """
        if not self.config.cover_config.enabled:
            return []

        cover = []
        for _ in range(count):
            msg = generate_cover_message(
                min_size=self.config.cover_config.min_size,
                max_size=self.config.cover_config.max_size,
            )
            self.stats.cover_messages += 1
            cover.append(msg)
        return cover

    def get_stats(self) -> dict:
        """Gibt Mixnet-Statistiken zurück."""
        return {
            "messages_in": self.stats.messages_in,
            "messages_out": self.stats.messages_out,
            "cover_messages": self.stats.cover_messages,
            "avg_delay_ms": self.stats.avg_delay_ms,
            "total_padding_bytes": self.stats.total_padding_bytes,
            "batches_created": self.batcher.batches_created,
        }


def get_mixnet_config(sector: str = "standard") -> MixnetConfig:
    """Gibt eine Mixnet-Konfiguration für einen Sektor zurück.

    Args:
        sector: Sektor-Name (fast, standard, high, mixnet)

    Returns:
        MixnetConfig
    """
    from .delay import get_delay_config

    if sector == "fast":
        return MixnetConfig(
            padding_enabled=False,
            delay_config=get_delay_config("fast"),
            batch_size=1,
            cover_config=CoverConfig(enabled=False),
        )
    elif sector == "standard":
        return MixnetConfig(
            padding_enabled=True,
            delay_config=get_delay_config("standard"),
            batch_size=5,
            cover_config=CoverConfig(enabled=False, rate_per_second=0.1),
        )
    elif sector == "high":
        return MixnetConfig(
            padding_enabled=True,
            delay_config=get_delay_config("high"),
            batch_size=10,
            cover_config=CoverConfig(enabled=True, rate_per_second=0.5),
        )
    elif sector == "mixnet":
        return MixnetConfig(
            padding_enabled=True,
            delay_config=get_delay_config("mixnet"),
            batch_size=20,
            cover_config=CoverConfig(enabled=True, rate_per_second=2.0),
        )
    else:
        return MixnetConfig()
