"""Batching für Erebos Network.

Sammelt Nachrichten und verarbeitet sie in Gruppen.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Batch:
    """Eine Gruppe von Nachrichten."""

    messages: list[bytes] = field(default_factory=list)
    batch_id: int = 0

    @property
    def size(self) -> int:
        """Anzahl Nachrichten im Batch."""
        return len(self.messages)

    def add(self, message: bytes) -> None:
        """Fügt eine Nachricht hinzu."""
        self.messages.append(message)

    def clear(self) -> None:
        """Leert den Batch."""
        self.messages.clear()


class Batcher:
    """Sammelt Nachrichten und gibt sie als Batch zurück.

    Args:
        max_size: Maximale Batch-Größe
        max_wait_ms: Maximale Wartezeit in Millisekunden
    """

    def __init__(self, max_size: int = 10, max_wait_ms: int = 1000):
        self.max_size = max_size
        self.max_wait_ms = max_wait_ms
        self._current_batch = Batch()
        self._batch_counter = 0
        self._lock = asyncio.Lock()

    async def add(self, message: bytes) -> Optional[Batch]:
        """Fügt eine Nachricht hinzu.

        Returns:
            Batch wenn voll, sonst None
        """
        async with self._lock:
            self._current_batch.add(message)

            if self._current_batch.size >= self.max_size:
                return await self._flush()

            return None

    async def _flush(self) -> Batch:
        """Leert den aktuellen Batch."""
        batch = self._current_batch
        self._current_batch = Batch()
        self._batch_counter += 1
        batch.batch_id = self._batch_counter
        return batch

    async def flush(self) -> Optional[Batch]:
        """Erzwingt ein Flush des aktuellen Batches."""
        async with self._lock:
            if self._current_batch.size > 0:
                return await self._flush()
            return None

    @property
    def pending(self) -> int:
        """Anzahl ausstehender Nachrichten."""
        return self._current_batch.size

    @property
    def batches_created(self) -> int:
        """Anzahl erstellter Batches."""
        return self._batch_counter
