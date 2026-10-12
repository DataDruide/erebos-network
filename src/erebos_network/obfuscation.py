"""Anwendungs-Obfuskation fuer Erebos Network.

Schuetzt gegen Anwendungs-Fingerprinting (L3-Ebene).
"""

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ObfuscationConfig:
    """Konfiguration fuer Obfuskation."""

    min_padding_ms: int = 0
    max_padding_ms: int = 100
    min_payload_size: int = 256
    max_payload_size: int = 1024
    add_timing_noise: bool = True
    add_size_noise: bool = True
    add_protocol_cover: bool = True


class ApplicationObfuscation:
    """Anwendungs-Obfuskation."""

    def __init__(self, config: Optional[ObfuscationConfig] = None):
        self.config = config or ObfuscationConfig()
        self.stats = {
            "messages_obfuscated": 0,
            "bytes_added_timing": 0,
            "bytes_added_size": 0,
            "cover_messages": 0,
        }

    def obfuscate(
        self,
        payload: bytes,
        protocol_hint: Optional[str] = None,
    ) -> bytes:
        """Obfuskiert eine Payload."""
        result = payload

        if self.config.add_size_noise:
            result = self._add_size_noise(result)

        if self.config.add_protocol_cover:
            result = self._add_protocol_cover(result, protocol_hint)

        self.stats["messages_obfuscated"] += 1
        return result

    def _add_size_noise(self, data: bytes) -> bytes:
        """Fuegt Size-Noise hinzu (zufaellige Groesse)."""
        min_size = self.config.min_payload_size
        max_size = self.config.max_payload_size

        if max_size <= min_size:
            target_size = min_size
        else:
            target_size = secrets.randbelow(max_size - min_size) + min_size

        if len(data) >= target_size:
            return data

        padding = secrets.token_bytes(target_size - len(data))
        self.stats["bytes_added_size"] += len(padding)
        return data + padding

    def _add_protocol_cover(
        self,
        data: bytes,
        protocol_hint: Optional[str],
    ) -> bytes:
        """Fuegt Protocol-Cover hinzu."""
        protocols = [b"HTTP/1.1", b"HTTPS", b"DNS", b"NTP", b"QUIC"]
        cover = secrets.choice(protocols)
        length = len(data).to_bytes(4, "big")
        return length + cover + b":" + data

    def add_timing_noise(self) -> float:
        """Fuegt Timing-Noise hinzu."""
        if not self.config.add_timing_noise:
            return 0.0

        min_ms = self.config.min_padding_ms
        max_ms = self.config.max_padding_ms

        if max_ms <= min_ms:
            delay_ms = min_ms
        else:
            delay_ms = secrets.randbelow(max_ms - min_ms) + min_ms

        self.stats["bytes_added_timing"] += 1
        return delay_ms / 1000.0

    def generate_cover_message(self) -> bytes:
        """Erzeugt eine Cover-Nachricht."""
        size = secrets.randbelow(768) + 256
        cover = secrets.token_bytes(size)
        self.stats["cover_messages"] += 1
        return cover

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "config": {
                "timing_noise": self.config.add_timing_noise,
                "size_noise": self.config.add_size_noise,
                "protocol_cover": self.config.add_protocol_cover,
            },
        }
