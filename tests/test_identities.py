"""Tests fuer create_identity + get_identity."""

import pytest
from erebos_network.forum_db import (
    create_identity, get_identity, get_db,
)


def test_create_identity_creates_all(temp_db, uuid_a):
    """create_identity erzeugt identity + mail_keys + forum_user."""
    result = create_identity(uuid_a)
    assert result["uuid"] == uuid_a
    assert result["email"].endswith("@erebos")
    assert result["forum_username"].startswith("erebos_")
    assert result["mail_keys"]["key_version"] >= 1
    assert result["forum_user"]["username"] == result["forum_username"]
    assert result["forum_user"]["password"] is not None


def test_create_identity_idempotent(temp_db, uuid_a):
    """Zweiter Aufruf aendert nichts (mail_keys, forum_user)."""
    r1 = create_identity(uuid_a)
    r2 = create_identity(uuid_a)
    assert r1["email"] == r2["email"]
    assert r1["forum_username"] == r2["forum_username"]
    # mail_keys: gleiche Version (nicht rotiert)
    assert r1["mail_keys"]["key_version"] == r2["mail_keys"]["key_version"]
    # forum_user: beim 2. Mal kein Passwort
    assert r2["forum_user"]["password"] is None


def test_get_identity_returns_data(temp_db, uuid_a):
    """get_identity liefert die gespeicherten Daten."""
    create_identity(uuid_a)
    ident = get_identity(uuid_a)
    assert ident is not None
    assert ident["uuid"] == uuid_a
    assert ident["email"].endswith("@erebos")
    assert ident["onboarded_at"] is not None


def test_get_identity_missing_returns_none(temp_db):
    """Unbekannte UUID -> None."""
    assert get_identity("00000000-0000-0000-0000-000000000000") is None


def test_forum_user_linked_to_uuid(temp_db, uuid_a):
    """users.mail_uuid ist gesetzt."""
    r = create_identity(uuid_a)
    conn = get_db()
    row = conn.execute(
        "SELECT mail_uuid FROM users WHERE username = ?",
        (r["forum_username"],),
    ).fetchone()
    assert row is not None
    assert row[0] == uuid_a


def test_email_format(temp_db, uuid_a):
    """E-Mail ist <kurzform>@erebos."""
    r = create_identity(uuid_a)
    short = uuid_a.replace("-", "")[:8]
    assert r["email"] == f"{short}@erebos"
