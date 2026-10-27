"""Tests fuer POST /mail/rotate + UI."""

import pytest
from erebos_network.landing_pages import (
    render_page, _render_rotate_confirm, _handle_rotate_post,
)


def _client_id():
    return "test-client-rotate-001"


def _uuid_for_client(client_id):
    import uuid as _uuid
    return str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))


def _make_request(path, method="GET", query="", client_id=""):
    """Rendert eine Seite (Bytes) und gibt sie zurueck."""
    return render_page(
        path=path,
        address="test.erebos",
        request_line=f"{method} {path} HTTP/1.1",
        method=method,
        body=b"",
        query=query,
        client_id=client_id,
    )


def test_rotate_confirm_page(temp_db):
    """GET /mail/rotate rendert Bestaetigungsseite."""
    html = _make_request("/mail/rotate", client_id=_client_id())
    text = html.decode("utf-8", "replace")
    assert "Schlüssel rotieren" in text or "rotieren" in text
    assert "Ja, jetzt rotieren" in text
    assert "Was passiert bei der Rotation" in text
    assert "Aktuelle Version" in text


def test_rotate_post_redirects(temp_db):
    """POST /mail/rotate -> REDIRECT:/mail?rotated=1."""
    body = _make_request("/mail/rotate", method="POST", client_id=_client_id())
    assert body.startswith(b"REDIRECT:"), f"Erwartet REDIRECT, got {body[:50]!r}"
    assert b"rotated=1" in body


def test_rotate_increments_version(temp_db):
    """Nach POST /mail/rotate ist key_version um 1 erhoeht."""
    from erebos_network.forum_db import get_mail_keys
    cid = _client_id()
    uuid = _uuid_for_client(cid)

    # Erst Key erzeugen (via /mail/rotate-GET)
    _make_request("/mail/rotate", client_id=cid)
    v1 = get_mail_keys(uuid)["key_version"]

    # Rotation ausfuehren
    _make_request("/mail/rotate", method="POST", client_id=cid)
    v2 = get_mail_keys(uuid)["key_version"]

    assert v2 == v1 + 1


def test_rotate_without_session_shows_error(temp_db):
    """POST /mail/rotate ohne client_id -> Fehlerseite (kein Crash)."""
    body = _make_request("/mail/rotate", method="POST", client_id="")
    text = body.decode("utf-8", "replace")
    assert "Fehler" in text or "Session" in text


def test_mail_page_shows_key_info(temp_db):
    """GET /mail zeigt Key-Info-Box mit Version + Rotate-Button."""
    html = _make_request("/mail", client_id=_client_id())
    text = html.decode("utf-8", "replace")
    assert "Schlüssel-Verwaltung" in text
    assert "Aktuelle Version" in text
    assert "Schlüssel rotieren" in text


def test_mail_page_shows_rotated_banner(temp_db):
    """GET /mail?rotated=1 zeigt Erfolgs-Banner."""
    html = _make_request("/mail", query="rotated=1", client_id=_client_id())
    text = html.decode("utf-8", "replace")
    assert "erfolgreich rotiert" in text


def test_rotate_rate_limit(temp_db, monkeypatch):
    """Nach 1x Rotate ist die naechste Rotation rate-limited."""
    import erebos_network.config as cfg
    monkeypatch.setattr(cfg, "ROTATE_RATE_LIMIT_SECONDS", 1)

    cid = _client_id()
    uuid = _uuid_for_client(cid)

    _make_request("/mail/rotate", method="GET", client_id=cid)
    _make_request("/mail/rotate", method="POST", client_id=cid)
    from erebos_network.forum_db import get_mail_keys
    assert get_mail_keys(uuid)["key_version"] == 2

    # Sofortige 2. Rotation -> rate-limited
    body = _make_request("/mail/rotate", method="POST", client_id=cid)
    text = body.decode("utf-8", "replace")
    assert "Zu viele Rotationen" in text
    assert get_mail_keys(uuid)["key_version"] == 2


def test_rotate_rate_limit_allows_after_window(temp_db, monkeypatch):
    """Nach Ablauf des Rate-Limits ist Rotation wieder erlaubt."""
    import erebos_network.config as cfg
    monkeypatch.setattr(cfg, "ROTATE_RATE_LIMIT_SECONDS", 0)

    cid = _client_id()
    uuid = _uuid_for_client(cid)

    _make_request("/mail/rotate", method="GET", client_id=cid)
    _make_request("/mail/rotate", method="POST", client_id=cid)
    _make_request("/mail/rotate", method="POST", client_id=cid)

    from erebos_network.forum_db import get_mail_keys
    assert get_mail_keys(uuid)["key_version"] == 3

