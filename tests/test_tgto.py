"""Tests fuer TGTO (Website Fingerprinting Defense)."""

import pytest

from erebos_network.tgto_defense import (
    SplashInjector,
    TGTO,
    TGTOConfig,
    TemplateLibrary,
    TemplateType,
    TraceMorpher,
    TraceShape,
    TrafficTemplate,
)


# --- TemplateLibrary ---

def test_library_init():
    """Library initialisiert."""
    lib = TemplateLibrary()
    assert len(lib.list_templates()) == 5


def test_library_get():
    """Library gibt Templates zurueck."""
    lib = TemplateLibrary()
    web = lib.get(TemplateType.WEB)
    assert web.template_type == TemplateType.WEB
    assert web.total_packets > 0


def test_library_baseline():
    """Baseline-Template."""
    lib = TemplateLibrary()
    b = lib.get(TemplateType.BASELINE)
    assert all(s == 64 for s in b.packet_sizes)


# --- TraceMorpher ---

def test_morpher_init():
    """Morpher initialisiert."""
    m = TraceMorpher()
    assert m.stats["morphs"] == 0


def test_morpher_resample_up():
    """Morpher fuellt auf."""
    config = TGTOConfig(template_type=TemplateType.WEB, resample=True, scale=False)
    m = TraceMorpher(config)
    trace = TraceShape(sizes=[100], directions=[1], times=[0.1])
    morphed = m.morph(trace)
    assert morphed.packet_count > 1


def test_morpher_resample_down():
    """Morpher kuerzt."""
    config = TGTOConfig(template_type=TemplateType.BASELINE, resample=True, scale=False)
    m = TraceMorpher(config)
    trace = TraceShape(sizes=[100] * 100, directions=[1] * 100, times=[0.1] * 100)
    morphed = m.morph(trace)
    # Baseline hat 20 Pakete
    assert morphed.packet_count == 20


def test_morpher_scale():
    """Morpher skaliert Groessen."""
    config = TGTOConfig(template_type=TemplateType.BULK, resample=False, scale=True)
    m = TraceMorpher(config)
    trace = TraceShape(sizes=[100] * 10, directions=[1] * 10, times=[0.1] * 10)
    morphed = m.morph(trace)
    # Bulk hat 1400er Pakete
    assert max(morphed.sizes) > 100


def test_morpher_stats():
    """Morpher-Statistiken."""
    m = TraceMorpher()
    trace = TraceShape(sizes=[100] * 5, directions=[1] * 5, times=[0.1] * 5)
    m.morph(trace)
    assert m.stats["morphs"] == 1


# --- SplashInjector ---

def test_splash_init():
    """Splash initialisiert."""
    s = SplashInjector()
    assert s.stats["splash_blocks"] == 0


def test_splash_injects():
    """Splash injiziert Bloecke."""
    config = TGTOConfig(splash_blocks_min=2, splash_blocks_max=4)
    s = SplashInjector(config)
    trace = TraceShape(sizes=[100] * 10, directions=[1] * 10, times=[0.1] * 10)
    result = s.inject(trace)
    assert result.packet_count > 10
    assert s.stats["splash_blocks"] >= 2


def test_splash_disabled():
    """Splash deaktiviert."""
    config = TGTOConfig(splash_enabled=False)
    s = SplashInjector(config)
    trace = TraceShape(sizes=[100] * 10, directions=[1] * 10, times=[0.1] * 10)
    result = s.inject(trace)
    assert result.packet_count == 10


def test_splash_stats():
    """Splash-Statistiken."""
    config = TGTOConfig(splash_blocks_min=1, splash_blocks_max=1)
    s = SplashInjector(config)
    trace = TraceShape(sizes=[100] * 5, directions=[1] * 5, times=[0.1] * 5)
    s.inject(trace)
    assert s.stats["splash_blocks"] == 1
    assert s.stats["splash_bytes"] > 0


# --- TGTO ---

def test_tgto_init():
    """TGTO initialisiert."""
    t = TGTO()
    assert t.config.enabled is True


def test_tgto_obfuscate():
    """TGTO obfuskiert."""
    t = TGTO()
    sizes = [100] * 10
    directions = [1] * 10
    times = [0.1] * 10
    result = t.obfuscate(sizes, directions, times)
    assert result.packet_count > 0


def test_tgto_disabled():
    """TGTO deaktiviert."""
    config = TGTOConfig(enabled=False)
    t = TGTO(config)
    sizes = [100] * 10
    result = t.obfuscate(sizes, [1] * 10)
    assert result.packet_count == 10


def test_tgto_different_templates():
    """TGTO mit verschiedenen Templates."""
    web_config = TGTOConfig(template_type=TemplateType.WEB)
    api_config = TGTOConfig(template_type=TemplateType.API)
    t_web = TGTO(web_config)
    t_api = TGTO(api_config)

    sizes = [100] * 50
    r_web = t_web.obfuscate(sizes, [1] * 50)
    r_api = t_api.obfuscate(sizes, [1] * 50)

    # Unterschiedliche Templates -> unterschiedliche Ergebnisse
    assert r_web.packet_count != r_api.packet_count or r_web.sizes != r_api.sizes


def test_tgto_stats():
    """TGTO-Statistiken."""
    t = TGTO()
    t.obfuscate([100] * 10, [1] * 10)
    stats = t.get_stats()
    assert "config" in stats
    assert "morpher" in stats
    assert "splash" in stats


def test_tgto_trace_shape():
    """TraceShape korrekt."""
    t = TGTO()
    result = t.obfuscate([100, 200, 300], [1, -1, 1], [0.1, 0.2, 0.3])
    assert isinstance(result, TraceShape)
    assert result.total_bytes > 0
