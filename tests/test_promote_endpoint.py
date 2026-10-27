"""Tests fuer /forum/admin/promote (HTTP-Route)."""

import pytest
from erebos_network.landing_pages import render_page
from erebos_network.forum_db import (
    get_user_role, get_db,
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


def _make_request(path, method="GET", body=b"", client_id="", username="", query=""):
    return render_page(
        path=path,
        address="test.erebos",
        request_line=f"{method} {path} HTTP/1.1",
        method=method,
        body=body,
        query=query,
        client_id=client_id,
        username=username,
    )


def test_promote_requires_admin(temp_db):
    """POST /forum/admin/promote ohne Admin -> 'Nicht erlaubt'."""
    body = b"username=bob&role=mod"
    resp = _make_request("/forum/admin/promote", method="POST", body=body, client_id="")
    text = resp.decode("utf-8", "replace")
    assert "Nicht erlaubt" in text


def test_promote_sets_role(temp_db):
    """Admin promoted User zu Mod."""
    conn = get_db()
    _insert_user(conn, "admin1", "admin")
    _insert_user(conn, "bob", "user")

    body = b"username=bob&role=mod"
    resp = _make_request(
        "/forum/admin/promote", method="POST", body=body,
        client_id="", username="admin1",
    )
    assert resp.startswith(b"REDIRECT:"), f"Erwartet REDIRECT, got {resp[:60]!r}"
    assert b"/forum/admin/authors" in resp
    assert get_user_role("bob") == "mod"


def test_promote_invalid_role(temp_db):
    """Ungueltige Rolle -> Fehlerseite."""
    conn = get_db()
    _insert_user(conn, "admin1", "admin")

    body = b"username=bob&role=superadmin"
    resp = _make_request(
        "/forum/admin/promote", method="POST", body=body,
        client_id="", username="admin1",
    )
    text = resp.decode("utf-8", "replace")
    assert "Ungueltige Rolle" in text or "Fehler" in text


def test_promote_demote_admin_to_user(temp_db):
    """Admin demoted sich selbst zu User."""
    conn = get_db()
    _insert_user(conn, "admin1", "admin")

    body = b"username=admin1&role=user"
    resp = _make_request(
        "/forum/admin/promote", method="POST", body=body,
        client_id="", username="admin1",
    )
    assert resp.startswith(b"REDIRECT:")
    assert get_user_role("admin1") == "user"


def test_promote_unknown_user(temp_db):
    """Unbekannter User -> Fehlerseite."""
    conn = get_db()
    _insert_user(conn, "admin1", "admin")

    body = b"username=nonexistent&role=mod"
    resp = _make_request(
        "/forum/admin/promote", method="POST", body=body,
        client_id="", username="admin1",
    )
    text = resp.decode("utf-8", "replace")
    assert "Fehler" in text or "nicht gefunden" in text
