"""Tests fuer Onboarding-Flow (Progressbar + Welcome)."""

import pytest
from erebos_network.landing_pages import render_page


def _client_id():
    return "test-client-onboard-001"


def _make_request(path, method="GET", query="", client_id=""):
    return render_page(
        path=path,
        address="test.erebos",
        request_line=f"{method} {path} HTTP/1.1",
        method=method,
        body=b"",
        query=query,
        client_id=client_id,
    )


def test_root_redirects_to_onboard_for_new_client(temp_db):
    """GET / ohne Identity -> REDIRECT:/onboard."""
    body = _make_request("/", client_id=_client_id())
    assert body.startswith(b"REDIRECT:/onboard"), f"Erwartet REDIRECT:/onboard, got {body[:60]!r}"


def test_onboard_page_renders(temp_db):
    """GET /onboard zeigt Progressbar-Seite."""
    html = _make_request("/onboard", client_id=_client_id())
    text = html.decode("utf-8", "replace")
    assert "EREBOS NETWORK" in text
    assert "Tunnel zum Rendezvous" in text
    assert "progress-fill" in text


def test_onboard_creates_identity(temp_db):
    """GET /onboard ruft create_identity auf."""
    from erebos_network.forum_db import get_identity
    import uuid as _uuid
    cid = _client_id()
    uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + cid))

    _make_request("/onboard", client_id=cid)

    ident = get_identity(uuid)
    assert ident is not None
    assert ident["onboarded_at"] is not None


def test_welcome_shows_identity(temp_db):
    """GET /welcome zeigt UUID, E-Mail, Forum-Username, Warnung."""
    cid = _client_id()
    _make_request("/onboard", client_id=cid)
    html = _make_request("/welcome", client_id=cid)
    text = html.decode("utf-8", "replace")
    assert "WILLKOMMEN BEI EREBOS" in text
    assert "@erebos" in text
    assert "WICHTIG - SCHREIB DAS AUF" in text
    assert "erebos_" in text  # Forum-Username


def test_welcome_ack_redirects_to_mail(temp_db):
    """POST /welcome/ack -> REDIRECT:/mail."""
    body = _make_request("/welcome/ack", method="POST", client_id=_client_id())
    assert body == b"REDIRECT:/mail"


def test_root_after_onboard_shows_landing(temp_db):
    """Nach Onboarding: GET / zeigt die normale Startseite, kein Redirect."""
    cid = _client_id()
    _make_request("/onboard", client_id=cid)
    body = _make_request("/", client_id=cid)
    # Kein Redirect mehr
    assert not body.startswith(b"REDIRECT:/onboard")
    # Sollte die Welcome-Seite sein (HTML)
    text = body.decode("utf-8", "replace")
    assert "EREBOS" in text or "Willkommen" in text


def test_full_onboarding_flow(temp_db):
    """Kompletter Flow: / -> /onboard -> /welcome -> /welcome/ack -> /mail."""
    cid = _client_id()

    # 1. / -> /onboard
    body = _make_request("/", client_id=cid)
    assert body.startswith(b"REDIRECT:/onboard")

    # 2. /onboard
    html = _make_request("/onboard", client_id=cid)
    assert "EREBOS NETWORK" in html.decode("utf-8", "replace")

    # 3. /welcome
    html = _make_request("/welcome", client_id=cid)
    text = html.decode("utf-8", "replace")
    assert "WILLKOMMEN BEI EREBOS" in text

    # 4. /welcome/ack
    body = _make_request("/welcome/ack", method="POST", client_id=cid)
    assert body == b"REDIRECT:/mail"

    # 5. / ist jetzt keine Redirect mehr
    body = _make_request("/", client_id=cid)
    assert not body.startswith(b"REDIRECT:/onboard")
