"""Tests fuer HS-Introduction-Rotation."""

import time

import pytest

from erebos_network.hs_rotation import (
    IntroPoint,
    IntroPointManager,
    RotationConfig,
    RotationReason,
)


# --- IntroPoint ---

def test_intro_point_creation():
    """Intro-Point wird erstellt."""
    p = IntroPoint(point_id="abc", address="intro-abc.erebos")
    assert p.point_id == "abc"
    assert p.is_healthy is True
    assert p.consecutive_failures == 0


def test_intro_point_age():
    """Intro-Point-Alter wird berechnet."""
    p = IntroPoint(point_id="abc", address="intro-abc.erebos")
    time.sleep(0.01)
    assert p.age_seconds > 0


def test_intro_point_success_rate():
    """Erfolgsrate wird berechnet."""
    p = IntroPoint(point_id="abc", address="intro-abc.erebos")
    p.total_successes = 9
    p.total_failures = 1
    assert p.success_rate == 0.9


# --- IntroPointManager ---

def test_manager_init():
    """Manager initialisiert."""
    m = IntroPointManager()
    assert m.point_count == 0


def test_manager_create_point():
    """Manager erstellt Intro-Points."""
    m = IntroPointManager()
    p = m.create_intro_point()
    assert p.point_id
    assert m.point_count == 1


def test_manager_ensure_points():
    """Manager stellt genug Points sicher."""
    m = IntroPointManager()
    points = m.ensure_intro_points()
    assert len(points) == m.config.num_intro_points


def test_manager_record_success():
    """Manager zeichnet Erfolg auf."""
    m = IntroPointManager()
    p = m.create_intro_point()
    m.record_success(p.point_id)
    assert p.total_successes == 1


def test_manager_record_failure():
    """Manager zeichnet Fehler auf."""
    m = IntroPointManager()
    p = m.create_intro_point()
    reason = m.record_failure(p.point_id)
    assert p.consecutive_failures == 1
    assert reason is None


def test_manager_failure_triggers_health_rotation():
    """3 Fehler triggern Health-Rotation."""
    m = IntroPointManager()
    p = m.create_intro_point()
    for _ in range(3):
        reason = m.record_failure(p.point_id)
    assert reason == RotationReason.HEALTH
    assert p.is_healthy is False


def test_manager_rotate():
    """Manager rotiert einen Point."""
    m = IntroPointManager()
    p = m.create_intro_point()
    new_p = m.rotate(p.point_id, RotationReason.MANUAL)
    assert new_p.point_id != p.point_id
    assert m.stats["points_rotated"] == 1


def test_manager_check_rotation_health():
    """Check erkennt Health-Rotation."""
    m = IntroPointManager()
    p = m.create_intro_point()
    for _ in range(3):
        m.record_failure(p.point_id)
    to_rotate = m.check_rotation_needed()
    assert any(pid == p.point_id for pid, _ in to_rotate)


def test_manager_check_rotation_age():
    """Check erkennt Age-Rotation."""
    m = IntroPointManager()
    m.config.max_age_seconds = 0  # Sofort alt
    p = m.create_intro_point()
    time.sleep(0.01)
    to_rotate = m.check_rotation_needed()
    assert any(reason == RotationReason.AGE for _, reason in to_rotate)


def test_manager_scheduled_rotation():
    """Scheduled Rotation funktioniert."""
    m = IntroPointManager()
    m.config.min_rotation_seconds = 0
    m.config.max_rotation_seconds = 0
    p = m.create_intro_point()
    m._next_rotation = time.time() - 1  # Bereits faellig
    to_rotate = m.check_rotation_needed()
    assert any(reason == RotationReason.SCHEDULED for _, reason in to_rotate)


# --- Intersection-Detection ---

def test_manager_record_session():
    """Manager zeichnet Sessions auf."""
    m = IntroPointManager()
    p = m.create_intro_point()
    m.record_session([p.point_id])
    assert len(m._sessions) == 1


def test_manager_no_intersection_few_sessions():
    """Keine Intersection bei wenigen Sessions."""
    m = IntroPointManager()
    m.record_session(["a"])
    m.record_session(["b"])
    suspicious = m.detect_intersection()
    assert suspicious == []


def test_manager_detects_intersection():
    """Intersection wird erkannt."""
    m = IntroPointManager()
    m.config.intersection_threshold = 3
    # Gleicher Point in 3 Sessions
    for _ in range(3):
        m.record_session(["same_point"])
    suspicious = m.detect_intersection()
    assert "same_point" in suspicious
    assert m.stats["intersections_detected"] == 1


def test_manager_no_false_positive():
    """Keine False-Positives."""
    m = IntroPointManager()
    m.config.intersection_threshold = 3
    m.record_session(["a"])
    m.record_session(["b"])
    m.record_session(["c"])
    suspicious = m.detect_intersection()
    assert suspicious == []


# --- Backoff ---

def test_retry_backoff():
    """Exponential Backoff funktioniert."""
    m = IntroPointManager()
    m.config.retry_base_seconds = 2.0
    m.config.retry_max_seconds = 30.0

    assert m.retry_backoff(0) == 2.0
    assert m.retry_backoff(1) == 4.0
    assert m.retry_backoff(2) == 8.0
    assert m.retry_backoff(10) == 30.0  # gecappt


def test_manager_stats():
    """Manager-Statistiken."""
    m = IntroPointManager()
    m.ensure_intro_points()
    stats = m.get_stats()
    assert stats["point_count"] == 3
    assert stats["healthy_count"] == 3
