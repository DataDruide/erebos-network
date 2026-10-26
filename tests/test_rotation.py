"""Tests for rotate_mail_keys + get_mail_keys_by_version."""

import pytest
from erebos_network.forum_db import (
    get_or_create_mail_keys, get_mail_keys, get_mail_keys_by_version,
    rotate_mail_keys, get_db,
)


def test_rotation_increments_version(temp_db, uuid_a):
    v1 = get_or_create_mail_keys(uuid_a)
    assert v1["key_version"] == 1
    v2 = rotate_mail_keys(uuid_a)
    assert v2["key_version"] == 2
    assert get_mail_keys(uuid_a)["key_version"] == 2


def test_rotation_creates_history_entries(temp_db, uuid_a):
    get_or_create_mail_keys(uuid_a)
    rotate_mail_keys(uuid_a)
    conn = get_db()
    rows = conn.execute(
        "SELECT key_version, revoked_at, superseded_by "
        "FROM mail_key_history WHERE uuid = ? ORDER BY key_version",
        (uuid_a,),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == 1
    assert rows[0][1] is not None
    assert rows[0][2] == "v2"
    assert rows[1][0] == 2
    assert rows[1][1] is None
    assert rows[1][2] is None


def test_rotation_preserves_privkeys_in_history(temp_db, uuid_a):
    get_or_create_mail_keys(uuid_a)
    rotate_mail_keys(uuid_a)
    hist_v1 = get_mail_keys_by_version(uuid_a, 1)
    assert hist_v1 is not None
    assert hist_v1["x25519_priv"]
    assert hist_v1["mlkem_priv"]
    assert hist_v1["ed25519_priv"]
    assert hist_v1["mldsa_priv"]


def test_rotation_changes_all_keys(temp_db, uuid_a):
    v1 = get_or_create_mail_keys(uuid_a)
    v2 = rotate_mail_keys(uuid_a)
    for field in ("x25519_pub", "mlkem_pub", "ed25519_pub", "mldsa_pub"):
        assert v1[field] != v2[field], f"{field} nicht rotiert"


def test_rotation_multiple_times(temp_db, uuid_a):
    get_or_create_mail_keys(uuid_a)
    rotate_mail_keys(uuid_a)
    rotate_mail_keys(uuid_a)
    assert get_mail_keys(uuid_a)["key_version"] == 3
    conn = get_db()
    rows = conn.execute(
        "SELECT key_version, revoked_at, superseded_by "
        "FROM mail_key_history WHERE uuid = ? ORDER BY key_version",
        (uuid_a,),
    ).fetchall()
    assert len(rows) == 3
    assert rows[0][2] == "v2"
    assert rows[1][2] == "v3"
    assert rows[2][1] is None


def test_rotation_unknown_uuid_raises(temp_db):
    with pytest.raises(ValueError, match="Keine mail_keys"):
        rotate_mail_keys("00000000-0000-0000-0000-000000000000")


def test_get_mail_keys_by_version_missing_returns_none(temp_db, uuid_a):
    get_or_create_mail_keys(uuid_a)
    assert get_mail_keys_by_version(uuid_a, 99) is None
