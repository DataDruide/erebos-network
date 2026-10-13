"""Tests fuer Predictive Perturbation (Augur)."""

import time

import pytest

from erebos_network.augur_defense import (
    AugurConfig,
    PredictivePerturbation,
    RateShaper,
    TrafficPredictor,
    TrafficSample,
)


# --- Traffic Predictor ---

def test_predictor_init():
    """Predictor initialisiert."""
    p = TrafficPredictor()
    assert p.sample_count == 0


def test_predictor_update():
    """Predictor akzeptiert Samples."""
    p = TrafficPredictor()
    p.update(TrafficSample(size=100, direction=1))
    assert p.sample_count == 1


def test_predictor_predict():
    """Predictor gibt Vorhersage."""
    p = TrafficPredictor()
    for i in range(10):
        p.update(TrafficSample(size=100, direction=1))
    size = p.predict_next_size()
    assert size > 0


# --- Predictive Perturbation ---

def test_augur_init():
    """Augur initialisiert."""
    ap = PredictivePerturbation()
    assert ap.stats["samples_processed"] == 0


def test_augur_process_outgoing():
    """Augur verarbeitet ausgehende Daten."""
    ap = PredictivePerturbation()
    packets = ap.process_outgoing(b"Hello, Erebos!")
    assert len(packets) >= 1
    assert packets[0] == b"Hello, Erebos!"
    assert ap.stats["samples_processed"] == 1


def test_augur_injects_perturbation():
    """Augur injiziert Perturbationen."""
    config = AugurConfig(
        perturbation_rate=1.0,
        rate_limit_per_second=1000.0,
    )
    ap = PredictivePerturbation(config)
    for _ in range(20):
        packets = ap.process_outgoing(b"x" * 100)
        time.sleep(0.001)
    assert ap.stats["perturbations_injected"] > 0


def test_augur_rate_limit():
    """Augur respektiert Rate-Limit."""
    config = AugurConfig(
        perturbation_rate=1.0,
        rate_limit_per_second=1.0,
    )
    ap = PredictivePerturbation(config)
    ap.process_outgoing(b"data")
    ap.process_outgoing(b"data")
    # Nur eine Perturbation pro Sekunde
    assert ap.stats["perturbations_injected"] <= 1


def test_augur_traffic_shape():
    """Augur gibt Traffic-Form zurueck."""
    ap = PredictivePerturbation()
    ap.process_outgoing(b"x" * 100)
    ap.process_outgoing(b"y" * 200)
    shape = ap.get_traffic_shape()
    assert shape["count"] == 2
    assert 100 in shape["sizes"]


def test_augur_stats():
    """Augur-Statistiken."""
    ap = PredictivePerturbation()
    ap.process_outgoing(b"data")
    stats = ap.get_stats()
    assert stats["samples_processed"] == 1
    assert "overhead_percent" in stats


# --- Rate Shaper ---

def test_rate_shaper_init():
    """Rate-Shaper initialisiert."""
    rs = RateShaper(target_rate_per_second=10.0)
    assert rs.get_stats()["packets_shaped"] == 0


def test_rate_shaper_allows():
    """Rate-Shaper erlaubt Pakete unter Limit."""
    rs = RateShaper(target_rate_per_second=100.0)
    # Token-Bucket startet leer, aber nach 0.01s sollte ein Token da sein
    time.sleep(0.02)
    assert rs.allow() is True


def test_rate_shaper_delays():
    """Rate-Shaper verzoegert bei Ueberschreitung."""
    rs = RateShaper(target_rate_per_second=1.0)
    # Verbrauche Token
    for _ in range(5):
        rs.allow()
    # Jetzt sollte es verzoegert werden
    assert rs.allow() is False
    assert rs.get_stats()["packets_delayed"] > 0


def test_rate_shaper_delay_for_next():
    """Rate-Shaper berechnet Verzoegerung."""
    rs = RateShaper(target_rate_per_second=1.0)
    for _ in range(5):
        rs.allow()
    delay = rs.delay_for_next()
    assert delay > 0


def test_rate_shaper_stats():
    """Rate-Shaper-Statistiken."""
    rs = RateShaper(target_rate_per_second=100.0)
    time.sleep(0.02)
    rs.allow()
    stats = rs.get_stats()
    assert stats["packets_shaped"] == 1
