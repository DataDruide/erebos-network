"""TCP-Normalisierung gegen Header-Tagging.

Schuetzt gegen covert channels in TCP/IP-Headern.
Basiert auf Rowland (2002), Giffin (2002), Linux TLS-Padding (2026).
"""

import hashlib
import logging
import random
import secrets
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TCPField(Enum):
    """Manipulierbare TCP/IP-Felder."""

    IP_ID = "ip_id"
    TCP_TIMESTAMP = "tcp_timestamp"
    TCP_WINDOW = "tcp_window"
    TCP_OPTIONS = "tcp_options"
    IP_TTL = "ip_ttl"
    TLS_RECORD_LENGTH = "tls_record_length"


@dataclass
class TCPNormalizerConfig:
    """Konfiguration fuer TCP-Normalisierung."""

    normalize_ip_id: bool = True
    normalize_timestamps: bool = True
    normalize_window: bool = True
    strip_options: bool = True
    normalize_ttl: bool = True
    pad_tls_records: bool = True
    standard_ttl: int = 64
    standard_window: int = 65535
    tls_padding_max: int = 256
    ip_id_random: bool = True


@dataclass
class TCPHeader:
    """Repraesentation eines TCP-Headers (vereinfacht)."""

    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    seq: int
    ack: int
    window: int
    ttl: int
    ip_id: int
    timestamp: Optional[int] = None
    options: bytes = b""
    flags: int = 0

    def to_dict(self) -> dict:
        """Konvertiert zu Dict."""
        return {
            "src": f"{self.src_ip}:{self.src_port}",
            "dst": f"{self.dst_ip}:{self.dst_port}",
            "seq": self.seq,
            "ack": self.ack,
            "window": self.window,
            "ttl": self.ttl,
            "ip_id": self.ip_id,
            "timestamp": self.timestamp,
            "options": self.options.hex(),
            "flags": self.flags,
        }


class IPIDNormalizer:
    """Normalisiert das IP Identification Field.

    Basiert auf Rowland (2002): IP-ID kann ASCII-Werte transportieren.
    """

    def __init__(self, config: Optional[TCPNormalizerConfig] = None):
        self.config = config or TCPNormalizerConfig()
        self.stats = {
            "normalized": 0,
            "randomized": 0,
        }

    def normalize(self, ip_id: int) -> int:
        """Normalisiert die IP-ID.

        Args:
            ip_id: Original IP-ID

        Returns:
            Normalisierte IP-ID
        """
        if not self.config.normalize_ip_id:
            return ip_id

        if self.config.ip_id_random:
            # Zufaellige IP-ID (nicht vorhersagbar)
            new_id = secrets.randbelow(65536)
            self.stats["randomized"] += 1
        else:
            # Standardwert
            new_id = 0

        self.stats["normalized"] += 1
        return new_id

    def get_stats(self) -> dict:
        return dict(self.stats)


class TimestampScrubber:
    """Normalisiert TCP-Timestamps.

    Basiert auf Giffin (2002): TCP-Timestamps koennen covert channels
    transportieren.
    """

    def __init__(self, config: Optional[TCPNormalizerConfig] = None):
        self.config = config or TCPNormalizerConfig()
        self._base_time = time.time()
        self.stats = {
            "scrubbed": 0,
        }

    def normalize(self, timestamp: Optional[int]) -> Optional[int]:
        """Normalisiert einen TCP-Timestamp.

        Args:
            timestamp: Original-Timestamp (oder None)

        Returns:
            Normalisierter Timestamp
        """
        if not self.config.normalize_timestamps:
            return timestamp

        if timestamp is None:
            return None

        # Standardisiere: Nur obere 16 Bits behalten, untere 16 randomisieren
        high_bits = timestamp & 0xFFFF0000
        low_bits = secrets.randbelow(65536)
        new_ts = high_bits | low_bits

        self.stats["scrubbed"] += 1
        return new_ts

    def get_stats(self) -> dict:
        return dict(self.stats)


class WindowNormalizer:
    """Normalisiert TCP-Fenster-Groessen.

    Basiert auf Patent US20210258346A1: TCP-Fenster koennen
    mit versteckten Tags markiert werden.
    """

    def __init__(self, config: Optional[TCPNormalizerConfig] = None):
        self.config = config or TCPNormalizerConfig()
        self.stats = {
            "normalized": 0,
        }

    def normalize(self, window: int) -> int:
        """Normalisiert die TCP-Fenster-Groesse.

        Args:
            window: Original-Fenster

        Returns:
            Normalisiertes Fenster
        """
        if not self.config.normalize_window:
            return window

        # Standardwert (oder naechster Standardwert)
        new_window = self.config.standard_window
        self.stats["normalized"] += 1
        return new_window

    def get_stats(self) -> dict:
        return dict(self.stats)


class OptionScrubber:
    """Entfernt ungewoehnliche TCP-Optionen."""

    def __init__(self, config: Optional[TCPNormalizerConfig] = None):
        self.config = config or TCPNormalizerConfig()
        self.stats = {
            "options_stripped": 0,
            "bytes_removed": 0,
        }

    def scrub(self, options: bytes) -> bytes:
        """Entfernt TCP-Optionen.

        Args:
            options: Original-Optionen

        Returns:
            Gesaeuberte Optionen (leer)
        """
        if not self.config.strip_options:
            return options

        if options:
            self.stats["options_stripped"] += 1
            self.stats["bytes_removed"] += len(options)

        return b""

    def get_stats(self) -> dict:
        return dict(self.stats)


class TLSRecordPadder:
    """TLS-Record-Padding.

    Basiert auf Linux-Kernel RFC (2026): TLS 1.3 Record Padding.
    """

    def __init__(self, config: Optional[TCPNormalizerConfig] = None):
        self.config = config or TCPNormalizerConfig()
        self.stats = {
            "records_padded": 0,
            "padding_bytes": 0,
        }

    def pad_record(self, record: bytes) -> bytes:
        """Polstert einen TLS-Record.

        Args:
            record: Original-Record

        Returns:
            Gepolsterter Record
        """
        if not self.config.pad_tls_records:
            return record

        # Zufaelliges Padding hinzufuegen
        padding_length = secrets.randbelow(self.config.tls_padding_max)
        if padding_length == 0:
            return record

        padding = secrets.token_bytes(padding_length)
        self.stats["records_padded"] += 1
        self.stats["padding_bytes"] += padding_length

        return record + padding

    def get_stats(self) -> dict:
        return dict(self.stats)


class TCPNormalizer:
    """Kombinierte TCP-Normalisierung.

    Schuetzt gegen:
    - IP-ID-Tagging (Rowland 2002)
    - TCP-Timestamp-Tagging (Giffin 2002)
    - TCP-Fenster-Tagging (Patent US20210258346A1)
    - TCP-Options-Tagging
    - TLS-Record-Length-Leakage
    """

    def __init__(self, config: Optional[TCPNormalizerConfig] = None):
        self.config = config or TCPNormalizerConfig()
        self.ip_id = IPIDNormalizer(self.config)
        self.timestamps = TimestampScrubber(self.config)
        self.window = WindowNormalizer(self.config)
        self.options = OptionScrubber(self.config)
        self.tls = TLSRecordPadder(self.config)
        self.stats = {
            "headers_normalized": 0,
        }

    def normalize_header(self, header: TCPHeader) -> TCPHeader:
        """Normalisiert einen TCP-Header.

        Args:
            header: Original-Header

        Returns:
            Normalisierter Header
        """
        normalized = TCPHeader(
            src_ip=header.src_ip,
            dst_ip=header.dst_ip,
            src_port=header.src_port,
            dst_port=header.dst_port,
            seq=header.seq,
            ack=header.ack,
            window=self.window.normalize(header.window),
            ttl=self.config.standard_ttl if self.config.normalize_ttl else header.ttl,
            ip_id=self.ip_id.normalize(header.ip_id),
            timestamp=self.timestamps.normalize(header.timestamp),
            options=self.options.scrub(header.options),
            flags=header.flags,
        )

        self.stats["headers_normalized"] += 1
        return normalized

    def normalize_tls_record(self, record: bytes) -> bytes:
        """Normalisiert einen TLS-Record."""
        return self.tls.pad_record(record)

    def get_stats(self) -> dict:
        """Kombinierte Statistiken."""
        return {
            "config": {
                "ip_id": self.config.normalize_ip_id,
                "timestamps": self.config.normalize_timestamps,
                "window": self.config.normalize_window,
                "options": self.config.strip_options,
                "tls_padding": self.config.pad_tls_records,
            },
            "headers_normalized": self.stats["headers_normalized"],
            "ip_id": self.ip_id.get_stats(),
            "timestamps": self.timestamps.get_stats(),
            "window": self.window.get_stats(),
            "options": self.options.get_stats(),
            "tls": self.tls.get_stats(),
        }
