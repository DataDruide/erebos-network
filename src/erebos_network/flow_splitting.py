"""Flow-Splitting gegen Shape-basierte Flow-Correlation.

Basiert auf "Shift Your Shape" (IEEE TDSC 2025/2026).
Standard: S=4 Entry-Gateways, I=2.0 Cover-Traffic.
PR-AUC sinkt von 0.9998 auf 0.0699.
"""

import hashlib
import logging
import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SplitConfig:
    """Konfiguration fuer Flow-Splitting.

    Standard: S=4, I=2.0 (Paper-Empfehlung).
    """

    num_gateways: int = 4  # S: Entry-Gateways
    cover_multiplier: float = 2.0  # I: Cover-Traffic-Faktor
    markov_p: float = 0.9  # Wahrscheinlichkeit fuer Serien
    min_series_length: int = 1
    max_series_length: int = 20
    randomize_params: bool = False  # Personalized Randomization
    randomization_range: float = 0.3  # ±30%


@dataclass
class FlowChunk:
    """Ein Chunk eines aufgeteilten Flows."""

    chunk_id: str
    gateway_id: int
    data: bytes
    sequence: int
    timestamp: float = field(default_factory=time.time)
    is_cover: bool = False

    @property
    def size(self) -> int:
        return len(self.data)


class FlowSplitter:
    """Flow-Splitter.

    Teilt einen Flow ueber S Entry-Gateways auf.
    Markov-Kette: mit p=0.9 bleibt der Flow beim selben Gateway
    fuer eine Serie (~10 Pakete), dann Wechsel.
    """

    def __init__(self, config: Optional[SplitConfig] = None):
        self.config = config or SplitConfig()
        self._current_gateway: int = 0
        self._series_count: int = 0
        self._target_series: int = 0
        self._sequence: int = 0
        self._choose_new_series()
        self.stats = {
            "chunks_created": 0,
            "gateway_switches": 0,
            "bytes_split": 0,
        }

    def _choose_new_series(self) -> None:
        """Waehlt eine neue Serienlaenge (Markov)."""
        self._target_series = max(
            self.config.min_series_length,
            min(
                secrets.randbelow(self.config.max_series_length)
                + self.config.min_series_length,
                self.config.max_series_length,
            ),
        )
        self._series_count = 0

    def _should_switch(self) -> bool:
        """Entscheidet, ob das Gateway gewechselt wird."""
        self._series_count += 1
        if self._series_count >= self._target_series:
            self._choose_new_series()
            return True
        # Markov: mit p=0.9 bleiben, sonst wechseln
        return random.random() > self.config.markov_p

    def _next_gateway(self) -> int:
        """Waehlt das naechste Gateway."""
        if self._should_switch():
            new_gw = secrets.randbelow(self.config.num_gateways)
            while (
                new_gw == self._current_gateway
                and self.config.num_gateways > 1
            ):
                new_gw = secrets.randbelow(self.config.num_gateways)
            self._current_gateway = new_gw
            self.stats["gateway_switches"] += 1
        return self._current_gateway

    def split(self, data: bytes, chunk_size: int = 256) -> list[FlowChunk]:
        """Teilt Daten auf mehrere Gateways auf.

        Args:
            data: Zu teilende Daten
            chunk_size: Groesse pro Chunk (default: 256 Bytes)

        Returns:
            Liste von FlowChunks
        """
        chunks = []
        for i in range(0, len(data), chunk_size):
            chunk_data = data[i:i+chunk_size]
            gateway = self._next_gateway()
            self._sequence += 1
            chunk = FlowChunk(
                chunk_id=hashlib.sha256(
                    f"{self._sequence}:{time.time()}".encode()
                ).hexdigest()[:16],
                gateway_id=gateway,
                data=chunk_data,
                sequence=self._sequence,
            )
            chunks.append(chunk)
            self.stats["chunks_created"] += 1
            self.stats["bytes_split"] += len(chunk_data)

        return chunks

    def reassemble(self, chunks: list[FlowChunk]) -> bytes:
        """Setzt Chunks wieder zusammen (Client-seitig)."""
        sorted_chunks = sorted(chunks, key=lambda c: c.sequence)
        return b"".join(c.data for c in sorted_chunks)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "current_gateway": self._current_gateway,
            "config": {
                "num_gateways": self.config.num_gateways,
                "markov_p": self.config.markov_p,
            },
        }


class CoverInjector:
    """Cover-Traffic-Injektor.

    Fuegt Cover-Traffic mit Faktor I hinzu.
    I=2.0 bedeutet: 2x so viele Cover-Pakete wie echte.
    """

    def __init__(self, config: Optional[SplitConfig] = None):
        self.config = config or SplitConfig()
        self._cover_sequence = 0
        self.stats = {
            "cover_chunks": 0,
            "cover_bytes": 0,
        }

    def inject(self, chunks: list[FlowChunk]) -> list[FlowChunk]:
        """Fuegt Cover-Traffic hinzu.

        Args:
            chunks: Echte Chunks

        Returns:
            Chunks + Cover-Chunks
        """
        if not chunks:
            return chunks

        num_cover = int(len(chunks) * self.config.cover_multiplier)
        avg_size = sum(c.size for c in chunks) // max(len(chunks), 1)

        result = list(chunks)
        for _ in range(num_cover):
            self._cover_sequence += 1
            size = max(
                64,
                min(
                    avg_size + secrets.randbelow(128) - 64,
                    1024,
                ),
            )
            cover = FlowChunk(
                chunk_id=hashlib.sha256(
                    f"cover:{self._cover_sequence}:{time.time()}".encode()
                ).hexdigest()[:16],
                gateway_id=secrets.randbelow(self.config.num_gateways),
                data=secrets.token_bytes(size),
                sequence=secrets.randbelow(10**6),
                is_cover=True,
            )
            result.append(cover)
            self.stats["cover_chunks"] += 1
            self.stats["cover_bytes"] += size

        random.shuffle(result)
        return result

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "cover_multiplier": self.config.cover_multiplier,
        }


class FlowSplittingDefense:
    """Kombinierte Verteidigung: Splitting + Cover.

    Standard: S=4, I=2.0 (Paper-Empfehlung).
    """

    def __init__(self, config: Optional[SplitConfig] = None):
        self.config = config or SplitConfig()
        self.splitter = FlowSplitter(self.config)
        self.injector = CoverInjector(self.config)

    def process(self, data: bytes) -> list[FlowChunk]:
        """Verarbeitet Daten: Splitting + Cover-Injection."""
        chunks = self.splitter.split(data)
        chunks = self.injector.inject(chunks)
        return chunks

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            "splitter": self.splitter.get_stats(),
            "injector": self.injector.get_stats(),
            "config": {
                "num_gateways": self.config.num_gateways,
                "cover_multiplier": self.config.cover_multiplier,
            },
        }
