"""Cover-Traffic für Erebos Network.

Erzeugt Dummy-Nachrichten, um echten Traffic zu verschleiern.
"""

import os
import random
import secrets
from dataclasses import dataclass


@dataclass
class CoverConfig:
    """Konfiguration für Cover-Traffic."""

    enabled: bool = True
    rate_per_second: float = 0.5  # Dummy-Nachrichten pro Sekunde
    min_size: int = 256
    max_size: int = 1024


def generate_cover_message(
    min_size: int = 256,
    max_size: int = 1024,
) -> bytes:
    """Erzeugt eine zufällige Cover-Nachricht.

    Args:
        min_size: Minimale Größe
        max_size: Maximale Größe

    Returns:
        Zufällige Bytes
    """
    size = random.randint(min_size, max_size)
    return secrets.token_bytes(size)


def generate_cover_batch(
    count: int,
    min_size: int = 256,
    max_size: int = 1024,
) -> list[bytes]:
    """Erzeugt mehrere Cover-Nachrichten.

    Args:
        count: Anzahl Nachrichten
        min_size: Minimale Größe
        max_size: Maximale Größe

    Returns:
        Liste von Cover-Nachrichten
    """
    return [generate_cover_message(min_size, max_size) for _ in range(count)]


def should_send_cover(config: CoverConfig, elapsed_seconds: float) -> bool:
    """Entscheidet, ob Cover-Traffic gesendet werden soll.

    Args:
        config: Cover-Konfiguration
        elapsed_seconds: Vergangene Zeit seit letztem Check

    Returns:
        True wenn Cover gesendet werden soll
    """
    if not config.enabled:
        return False

    expected = config.rate_per_second * elapsed_seconds
    return random.random() < expected
