"""Tests fuer Rollen-System (users.role + promote)."""

import pytest
from erebos_network.forum_db import (
    get_user_role, set_user_role, is_moderator,
    promote_first_user_to_admin, create_identity,
    get_db,
)


def _insert_user(conn, username: str, role: str = "user") -> None:
    """Fuegt einen User mit Rolle ein."""
    import hashlib
    import secrets
    import time
    pw = secrets.token_urlsafe(16)
    salt = secrets.token_hex(16)
    pw_hash = hashlib.sha256((salt + pw).encode()).hexdigest()
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password_hash, salt, created_at, role) "
        "VALUES (?, ?, ?, ?, ?)",
        (username, pw_hash, salt, time.time(), role),
    )
    conn.commit()


# ============================================================
# get_user_role / set_user_role / is_moderator
# ============================================================

def test_get_user_role_default(temp_db):
    """Unbekannter User -> 'user'."""
    assert get_user_role("unknown") == "user"
    assert get_user_role("") == "user"
    assert get_user_role(None) == "user"


def test_set_user_role_roundtrip(temp_db):
    """set_user_role + get_user_role."""
    conn = get_db()
    _insert_user(conn, "alice", "user")
    assert get_user_role("alice") == "user"

    assert set_user_role("alice", "mod") is True
    assert get_user_role("alice") == "mod"

    assert set_user_role("alice", "admin") is True
    assert get_user_role("alice") == "admin"

    assert set_user_role("alice", "user") is True
    assert get_user_role("alice") == "user"


def test_set_user_role_invalid(temp_db):
    """Ungueltige Rolle -> False."""
    conn = get_db()
    _insert_user(conn, "bob", "user")
    assert set_user_role("bob", "superadmin") is False
    assert get_user_role("bob") == "user"


def test_set_user_role_unknown_user(temp_db):
    """Unbekannter User -> False."""
    assert set_user_role("unknown", "admin") is False


def test_is_moderator(temp_db):
    """is_moderator: True fuer mod + admin."""
    conn = get_db()
    _insert_user(conn, "user1", "user")
    _insert_user(conn, "mod1", "mod")
    _insert_user(conn, "admin1", "admin")

    assert is_moderator("user1") is False
    assert is_moderator("mod1") is True
    assert is_moderator("admin1") is True
    assert is_moderator("unknown") is False


# ============================================================
# promote_first_user_to_admin
# ============================================================

def test_promote_first_user_to_admin(temp_db):
    """Erster User wird Admin."""
    conn = get_db()
    # Noch keine User -> ""
    assert promote_first_user_to_admin() == ""

    _insert_user(conn, "alice", "user")
    assert promote_first_user_to_admin() == "alice"
    assert get_user_role("alice") == "admin"


def test_promote_first_user_idempotent(temp_db):
    """Zweiter Aufruf aendert nichts (Admin existiert schon)."""
    conn = get_db()
    _insert_user(conn, "alice", "user")
    _insert_user(conn, "bob", "user")

    assert promote_first_user_to_admin() == "alice"
    assert get_user_role("alice") == "admin"

    # Zweiter Aufruf: kein neuer Admin
    assert promote_first_user_to_admin() == ""
    assert get_user_role("bob") == "user"


def test_create_identity_promotes_first(temp_db, uuid_a):
    """create_identity: erster User wird Admin."""
    result = create_identity(uuid_a)
    assert result["forum_user"]["role"] == "admin"
    assert get_user_role(result["forum_username"]) == "admin"


def test_create_identity_second_user_normal(temp_db, uuid_a, uuid_b):
    """Zweiter User wird 'user', nicht Admin."""
    r1 = create_identity(uuid_a)
    r2 = create_identity(uuid_b)
    assert r1["forum_user"]["role"] == "admin"
    assert r2["forum_user"]["role"] == "user"
    assert get_user_role(r1["forum_username"]) == "admin"
    assert get_user_role(r2["forum_username"]) == "user"
