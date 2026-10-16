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
    """Konfiguration fuer Cover-Traffic.

    mode:
      - "poisson": exponentialverteilte Intervalle (Standard)
      - "burst":   kurze Bursts mit Pausen (bessere WF-Resistenz)
      - "constant": konstantes Intervall (max. Unobservability, hoher Overhead)
    """

    enabled: bool = True
    rate_per_second: float = 0.5
    min_size: int = 256
    max_size: int = 1024
    constant: bool = False
    mode: str = "poisson"
    burst_size: int = 5
    burst_pause_seconds: float = 2.0


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

class TunnelCoverInjector:
    """Sendet echten Cover-Traffic ueber einen ErebosTunnelClient.

    Anders als ConstantCoverTraffic (das nur Bytes erzeugt), sendet
    dieser Injector die Frames wirklich ueber einen bestehenden
    verschluesselten Tunnel. Der Empfaenger erkennt FRAME_COVER und
    verwirft die Payload.

    Modi:
      - poisson: exponentialverteilte Intervalle
      - burst:   N Frames schnell hintereinander, dann Pause
      - constant: konstantes Intervall (1/rate)
    """

    def __init__(self, tunnel, config: Optional[CoverConfig] = None):
        self.tunnel = tunnel
        self.config = config or CoverConfig()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.stats = {
            "frames_sent": 0,
            "bytes_sent": 0,
            "errors": 0,
            "started_at": 0.0,
        }

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.stats["started_at"] = time.time()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"TunnelCoverInjector gestartet "
            f"(mode={self.config.mode}, rate={self.config.rate_per_second}/s)"
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TunnelCoverInjector gestoppt")

    async def _send_one(self) -> None:
        """Sendet einen einzelnen Cover-Frame."""
        from .tunnel import FRAME_COVER
        msg = generate_cover_message(
            self.config.min_size,
            self.config.max_size,
        )
        await self.tunnel.send_typed(FRAME_COVER, msg)
        self.stats["frames_sent"] += 1
        self.stats["bytes_sent"] += len(msg)

    async def _run_loop(self) -> None:
        mode = self.config.mode
        try:
            while self._running:
                if mode == "burst":
                    # Burst: N Frames schnell, dann Pause
                    for _ in range(self.config.burst_size):
                        if not self._running:
                            return
                        try:
                            await self._send_one()
                        except Exception as e:
                            self.stats["errors"] += 1
                            logger.debug(f"Cover send error: {e}")
                            return
                        await asyncio.sleep(0.02)  # 20ms zwischen Burst-Frames
                    await asyncio.sleep(self.config.burst_pause_seconds)
                elif mode == "constant":
                    interval = 1.0 / max(self.config.rate_per_second, 0.001)
                    await asyncio.sleep(interval)
                    try:
                        await self._send_one()
                    except Exception as e:
                        self.stats["errors"] += 1
                        logger.debug(f"Cover send error: {e}")
                        return
                else:  # poisson
                    delay = random.expovariate(
                        max(self.config.rate_per_second, 0.001)
                    )
                    await asyncio.sleep(delay)
                    try:
                        await self._send_one()
                    except Exception as e:
                        self.stats["errors"] += 1
                        logger.debug(f"Cover send error: {e}")
                        return
        except asyncio.CancelledError:
            pass

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def uptime_seconds(self) -> float:
        if self.stats["started_at"] == 0:
            return 0.0
        return time.time() - self.stats["started_at"]

    def get_stats(self) -> dict:
        return {
            **self.stats,
            "running": self._running,
            "mode": self.config.mode,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "rate_per_second": self.config.rate_per_second,
        }

