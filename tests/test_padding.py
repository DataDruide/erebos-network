"""Tests für Padding."""

import pytest

from erebos_network.padding import (
    DEFAULT_BLOCK_SIZE,
    PaddedMessage,
    pad_message,
    pad_to_fixed_size,
    unpad_message,
)


def test_pad_message_basic():
    """Basic Padding funktioniert."""
    data = b"Hello, Erebos!"
    padded = pad_message(data, block_size=1024)
    assert padded.original_size == 14
    assert padded.padded_size == 1024
    assert len(padded.data) == 1024
    assert padded.data[:14] == data


def test_pad_message_overhead():
    """Overhead wird berechnet."""
    data = b"x" * 100
    padded = pad_message(data, block_size=1024)
    assert padded.overhead == 924
    assert padded.overhead_percent == 924.0


def test_pad_message_too_large():
    """Zu große Nachrichten werfen Fehler."""
    data = b"x" * 100000
    with pytest.raises(ValueError):
        pad_message(data, block_size=1024, max_size=65536)


def test_unpad_message():
    """Unpad gibt Original zurück."""
    data = b"Hello, Erebos!"
    padded = pad_message(data, block_size=1024)
    unpadded = unpad_message(padded, padded.original_size)
    assert unpadded == data


def test_pad_to_fixed_size():
    """Padding auf feste Größe."""
    data = b"Test"
    padded = pad_to_fixed_size(data, 256)
    assert len(padded) == 256
    assert padded[:4] == data


def test_padding_random():
    """Padding-Bytes sind zufällig."""
    data = b"Same message"
    p1 = pad_message(data, block_size=1024)
    p2 = pad_message(data, block_size=1024)
    assert p1.data != p2.data  # Unterschiedliche Padding-Bytes
    assert p1.data[:12] == p2.data[:12]  # Gleicher Anfang
