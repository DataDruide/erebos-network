"""Tests fuer find_expiring_keys + auto_rotate_expiring_keys."""

import time
import pytest
from erebos_network.forum_db import (
    get_or_create_mail_keys, get_mail_keys,
    find_expiring_keys, auto_rotate_expiring_keys,
)


def _set_valid_until(uuid: str, days_from_now: float) -> None:
    """Setzt valid_until auf N Tage ab jetzt (negativ = Vergangenheit)."""
    from erebos_network.forum_db import get_db
    conn = get_db()
    conn.execute(
        "UPDATE mail_keys SET valid_until = ? WHERE uuid = ?",
        (time.time() + days_from_now * 86400, uuid),
    )
    conn.commit()


def test_find_expiring_keys_empty(temp_db):
    """Frische DB: keine ablaufenden Keys."""
    assert find_expiring_keys() == []


def test_find_expiring_keys_finds_expiring(temp_db, uuid_a):
    """Key in 3 Tagen -> wird gefunden (Default-Schwelle 7 Tage)."""
    get_or_create_mail_keys(uuid_a)
    _set_valid_until(uuid_a, 3)
    expiring = find_expiring_keys()
    assert len(expiring) == 1
    assert expiring[0]["uuid"] == uuid_a
    assert expiring[0]["days_left"] == pytest.approx(3, abs=0.1)


def test_find_expiring_keys_ignores_far_future(temp_db, uuid_a):
    """Key in 30 Tagen -> nicht gefunden (Default-Schwelle 7 Tage)."""
    get_or_create_mail_keys(uuid_a)
    _set_valid_until(uuid_a, 30)
    assert find_expiring_keys() == []


def test_find_expiring_keys_custom_threshold(temp_db, uuid_a):
    """Key in 3 Tagen, Schwelle 5 Tage -> gefunden."""
    get_or_create_mail_keys(uuid_a)
    _set_valid_until(uuid_a, 3)
    expiring = find_expiring_keys(days_before=5)
    assert len(expiring) == 1


def test_auto_rotate_rotates_expiring(temp_db, uuid_a):
    """Ablaufender Key wird rotiert."""
    keys = get_or_create_mail_keys(uuid_a)
    v1 = keys["key_version"]
    _set_valid_until(uuid_a, 3)

    result = auto_rotate_expiring_keys()
    assert len(result["rotated"]) == 1
    assert result["rotated"][0] == uuid_a
    assert result["failed"] == []

    new_keys = get_mail_keys(uuid_a)
    assert new_keys["key_version"] == v1 + 1


def test_auto_rotate_skips_far_future(temp_db, uuid_a):
    """Key in 30 Tagen wird nicht rotiert."""
    get_or_create_mail_keys(uuid_a)
    _set_valid_until(uuid_a, 30)

    result = auto_rotate_expiring_keys()
    assert result["rotated"] == []


def test_auto_rotate_dry_run(temp_db, uuid_a):
    """dry_run=True rotiert nicht, listet nur."""
    get_or_create_mail_keys(uuid_a)
    _set_valid_until(uuid_a, 3)

    result = auto_rotate_expiring_keys(dry_run=True)
    assert result["rotated"] == []
    assert len(result["skipped"]) == 1
    assert result["skipped"][0] == uuid_a

    keys = get_mail_keys(uuid_a)
    assert keys["key_version"] == 1


def test_auto_rotate_bypasses_rate_limit(temp_db, uuid_a):
    """Auto-Rotation umgeht das Rate-Limit (kein 429)."""
    get_or_create_mail_keys(uuid_a)

    # 3x auto-rotieren (jedes Mal valid_until zuruecksetzen)
    for i in range(3):
        _set_valid_until(uuid_a, 3)
        result = auto_rotate_expiring_keys()
        assert len(result["rotated"]) == 1, f"Durchlauf {i} fehlgeschlagen"

    # Rate-Limit-Tabelle sollte leer sein (auto_rotate ruft record_rotate nicht auf)
    from erebos_network.forum_db import get_db
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM rotate_rate_limit").fetchone()[0]
    assert count == 0
