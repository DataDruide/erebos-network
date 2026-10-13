"""Tests fuer TCP-Normalisierung."""

import pytest

from erebos_network.tcp_normalizer import (
    IPIDNormalizer,
    OptionScrubber,
    TCPHeader,
    TCPNormalizer,
    TCPNormalizerConfig,
    TLSRecordPadder,
    TimestampScrubber,
    WindowNormalizer,
)


# --- IPIDNormalizer ---

def test_ipid_init():
    """IP-ID-Normalizer initialisiert."""
    n = IPIDNormalizer()
    assert n.stats["normalized"] == 0


def test_ipid_normalizes():
    """IP-ID wird normalisiert."""
    n = IPIDNormalizer()
    original = 12345
    result = n.normalize(original)
    assert result != original or n.stats["normalized"] == 1


def test_ipid_random():
    """IP-ID wird randomisiert."""
    config = TCPNormalizerConfig(ip_id_random=True)
    n = IPIDNormalizer(config)
    results = [n.normalize(1000) for _ in range(10)]
    # Sollte unterschiedliche Werte geben
    assert len(set(results)) > 1


def test_ipid_disabled():
    """IP-ID-Normalisierung deaktiviert."""
    config = TCPNormalizerConfig(normalize_ip_id=False)
    n = IPIDNormalizer(config)
    assert n.normalize(12345) == 12345


# --- TimestampScrubber ---

def test_timestamp_init():
    """Timestamp-Scrubber initialisiert."""
    s = TimestampScrubber()
    assert s.stats["scrubbed"] == 0


def test_timestamp_scrubs():
    """Timestamp wird gesaeubert."""
    s = TimestampScrubber()
    original = 0x12345678
    result = s.normalize(original)
    assert result is not None
    # Obere Bits sollten erhalten sein
    assert (result & 0xFFFF0000) == (original & 0xFFFF0000)


def test_timestamp_none():
    """Timestamp None bleibt None."""
    s = TimestampScrubber()
    assert s.normalize(None) is None


# --- WindowNormalizer ---

def test_window_init():
    """Window-Normalizer initialisiert."""
    w = WindowNormalizer()
    assert w.stats["normalized"] == 0


def test_window_normalizes():
    """Window wird normalisiert."""
    config = TCPNormalizerConfig(standard_window=65535)
    w = WindowNormalizer(config)
    assert w.normalize(12345) == 65535


# --- OptionScrubber ---

def test_option_init():
    """Option-Scrubber initialisiert."""
    o = OptionScrubber()
    assert o.stats["options_stripped"] == 0


def test_option_strips():
    """Optionen werden entfernt."""
    o = OptionScrubber()
    result = o.scrub(b"\x01\x02\x03\x04")
    assert result == b""
    assert o.stats["options_stripped"] == 1


def test_option_no_strip():
    """Optionen bleiben wenn deaktiviert."""
    config = TCPNormalizerConfig(strip_options=False)
    o = OptionScrubber(config)
    original = b"\x01\x02"
    assert o.scrub(original) == original


# --- TLSRecordPadder ---

def test_tls_init():
    """TLS-Padder initialisiert."""
    t = TLSRecordPadder()
    assert t.stats["records_padded"] == 0


def test_tls_pads():
    """TLS-Record wird gepolstert."""
    config = TCPNormalizerConfig(tls_padding_max=256)
    t = TLSRecordPadder(config)
    record = b"Hello"
    result = t.pad_record(record)
    assert len(result) >= len(record)


# --- TCPNormalizer ---

def test_normalizer_init():
    """Normalizer initialisiert."""
    n = TCPNormalizer()
    assert n.stats["headers_normalized"] == 0


def test_normalizer_header():
    """Header wird normalisiert."""
    n = TCPNormalizer()
    header = TCPHeader(
        src_ip="192.168.1.1",
        dst_ip="10.0.0.1",
        src_port=12345,
        dst_port=80,
        seq=1000,
        ack=2000,
        window=12345,
        ttl=128,
        ip_id=54321,
        timestamp=0xABCDEF00,
        options=b"\x01\x02\x03",
    )
    result = n.normalize_header(header)
    assert result.window == n.config.standard_window
    assert result.ttl == n.config.standard_ttl
    assert result.options == b""
    assert n.stats["headers_normalized"] == 1


def test_normalizer_tls():
    """TLS-Record wird normalisiert."""
    n = TCPNormalizer()
    record = b"TLS data"
    result = n.normalize_tls_record(record)
    assert len(result) >= len(record)


def test_normalizer_stats():
    """Normalizer-Statistiken."""
    n = TCPNormalizer()
    header = TCPHeader(
        src_ip="192.168.1.1",
        dst_ip="10.0.0.1",
        src_port=12345,
        dst_port=80,
        seq=1000,
        ack=2000,
        window=12345,
        ttl=128,
        ip_id=54321,
    )
    n.normalize_header(header)
    stats = n.get_stats()
    assert stats["headers_normalized"] == 1
    assert "ip_id" in stats
    assert "timestamps" in stats
    assert "window" in stats
    assert "options" in stats
    assert "tls" in stats


def test_normalizer_disabled():
    """Normalizer deaktiviert."""
    config = TCPNormalizerConfig(
        normalize_ip_id=False,
        normalize_timestamps=False,
        normalize_window=False,
        strip_options=False,
        normalize_ttl=False,
    )
    n = TCPNormalizer(config)
    header = TCPHeader(
        src_ip="192.168.1.1",
        dst_ip="10.0.0.1",
        src_port=12345,
        dst_port=80,
        seq=1000,
        ack=2000,
        window=12345,
        ttl=128,
        ip_id=54321,
        timestamp=0xABCDEF00,
        options=b"\x01\x02",
    )
    result = n.normalize_header(header)
    assert result.window == 12345
    assert result.ttl == 128
    assert result.options == b"\x01\x02"
