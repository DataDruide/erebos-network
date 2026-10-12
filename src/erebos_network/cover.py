"""Cover-Traffic fuer Erebos Network.

Erzeugt Dummy-Nachrichten, um echten Traffic zu verschleiern.

Erweitert um konstanten Cover-Traffic (Unobservability).
"""

import asyncio
import logging
import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CoverConfig:
    """Konfiguration fuer Cover-Traffic."""

    enabled: bool = True
    rate_per_second: float = 0.5  # Dummy-Nachrichten pro Sekunde
    min_size: int = 256
    max_size: int = 1024
    constant: bool = False  # Konstant statt zufaellig


def generate_cover_message(
    min_size: int = 256,
    max_size: int = 1024,
) -> bytes:
    """Erzeugt eine zufaellige Cover-Nachricht."""
    size = random.randint(min_size, max_size)
    return secrets.token_bytes(size)


def generate_cover_batch(
    count: int,
    min_size: int = 256,
    max_size: int = 1024,
) -> list[bytes]:
    """Erzeugt mehrere Cover-Nachrichten."""
    return [generate_cover_message(min_size, max_size) for _ in range(count)]


def should_send_cover(config: CoverConfig, elapsed_seconds: float) -> bool:
    """Entscheidet, ob Cover-Traffic gesendet werden soll."""
    if not config.enabled:
        return False

    expected = config.rate_per_second * elapsed_seconds
    return random.random() < expected


class ConstantCoverTraffic:
    """Konstanter Cover-Traffic.

    Sendet kontinuierlich Cover-Nachrichten mit einer festen Rate,
    unabhaengig von echtem Traffic. Das verhindert, dass ein
    Beobachter erkennen kann, wann echte Kommunikation stattfindet.

    Basiert auf Poisson-Prozess (exponentialverteilte Zwischenankunftszeiten).
    """

    def __init__(self, config: Optional[CoverConfig] = None):
        self.config = config or CoverConfig()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.stats = {
            "messages_sent": 0,
            "bytes_sent": 0,
            "started_at": 0.0,
        }

    async def start(self) -> None:
        """Startet konstanten Cover-Traffic."""
        if self._running:
            return
        self._running = True
        self.stats["started_at"] = time.time()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Konstanter Cover-Traffic gestartet "
            f"({self.config.rate_per_second}/s)"
        )

    async def stop(self) -> None:
        """Stoppt Cover-Traffic."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Konstanter Cover-Traffic gestoppt")

    async def _run_loop(self) -> None:
        """Haupt-Loop: sendet Cover-Nachrichten mit Poisson-Verteilung."""
        while self._running:
            try:
                # Exponentialverteilte Zwischenankunftszeit
                delay = random.expovariate(self.config.rate_per_second)
                await asyncio.sleep(delay)

                msg = generate_cover_message(
                    self.config.min_size,
                    self.config.max_size,
                )
                self.stats["messages_sent"] += 1
                self.stats["bytes_sent"] += len(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cover-Traffic Fehler: {e}")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def uptime_seconds(self) -> float:
        if self.stats["started_at"] == 0:
            return 0.0
        return time.time() - self.stats["started_at"]

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "running": self._running,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "rate_per_second": self.config.rate_per_second,
        }
