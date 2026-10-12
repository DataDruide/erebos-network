"""Padding für Erebos Network.

Macht alle Nachrichten gleich groß, um Traffic-Analyse zu verhindern.
"""

import os
import secrets
from dataclasses import dataclass


# Standard-Blockgrößen (in Bytes)
DEFAULT_BLOCK_SIZE = 1024
DEFAULT_MAX_SIZE = 65536


@dataclass
class PaddedMessage:
    """Eine gepolsterte Nachricht."""

    data: bytes
    original_size: int
    padded_size: int

    @property
    def overhead(self) -> int:
        """Overhead durch Padding."""
        return self.padded_size - self.original_size

    @property
    def overhead_percent(self) -> float:
        """Overhead in Prozent."""
        if self.original_size == 0:
            return 0.0
        return (self.overhead / self.original_size) * 100


def pad_message(
    data: bytes,
    block_size: int = DEFAULT_BLOCK_SIZE,
    max_size: int = DEFAULT_MAX_SIZE,
) -> PaddedMessage:
    """Polstert eine Nachricht auf die nächste Blockgröße.

    Args:
        data: Original-Nachricht
        block_size: Blockgröße (Standard: 1024)
        max_size: Maximale Größe (Standard: 65536)

    Returns:
        PaddedMessage mit aufgefüllten Daten

    Raises:
        ValueError: Wenn Nachricht zu groß
    """
    original_size = len(data)

    if original_size > max_size:
        raise ValueError(
            f"Nachricht zu groß: {original_size} > {max_size}"
        )

    # Zielgröße: nächste Blockgröße
    target_size = ((original_size // block_size) + 1) * block_size
    target_size = min(target_size, max_size)

    # Padding mit kryptographisch sicheren Zufallsbytes
    padding_length = target_size - original_size
    padding = secrets.token_bytes(padding_length)

    return PaddedMessage(
        data=data + padding,
        original_size=original_size,
        padded_size=target_size,
    )


def unpad_message(padded: PaddedMessage, original_size: int) -> bytes:
    """Entfernt Padding.

    Args:
        padded: Gepolsterte Nachricht
        original_size: Ursprüngliche Größe

    Returns:
        Original-Nachricht
    """
    return padded.data[:original_size]


def pad_to_fixed_size(data: bytes, target_size: int) -> bytes:
    """Polstert auf exakte Zielgröße.

    Args:
        data: Original-Nachricht
        target_size: Zielgröße in Bytes

    Returns:
        Gepolsterte Nachricht

    Raises:
        ValueError: Wenn Nachricht größer als Ziel
    """
    if len(data) > target_size:
        raise ValueError(
            f"Nachricht ({len(data)}) größer als Ziel ({target_size})"
        )

    padding_length = target_size - len(data)
    return data + secrets.token_bytes(padding_length)
