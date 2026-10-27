"""Tests fuer Identitaets-Recovery (UUID/E-Mail eingeben)."""

import uuid as _uuid
from erebos_network.landing_pages import render_page
from erebos_network.forum_db import create_identity, get_identity


def _client_id():
    return "test-client-recover-001"


def _make_request(path, method="GET", body=b"", client_id="", query=""):
    return render_page(
        path=path,
        address="test.erebos",
        request_line=f"{method} {path} HTTP/1.1",
        method=method,
        body=body,
        query=query,
        client_id=client_id,
    )


def test_recover_form_renders(temp_db):
    """GET /recover zeigt Formular."""
    html = _make_request("/recover", client_id="")
    text = html.decode("utf-8", "replace")
    assert "IDENTITAET WIEDERHERSTELLEN" in text
    assert "UUID oder E-Mail" in text


def test_recover_with_uuid(temp_db, uuid_a):
    """POST /recover mit UUID -> REDIRECT:/mail + SET_IDENTITY."""
    create_identity(uuid_a)
    body = b"identifier=" + uuid_a.encode()
    resp = _make_request("/recover", method="POST", body=body, client_id="")
    assert resp.startswith(b"REDIRECT:/mail")
    assert b"SET_IDENTITY:" in resp
    assert uuid_a.encode() in resp


def test_recover_with_email(temp_db, uuid_a):
    """POST /recover mit E-Mail -> REDIRECT:/mail + SET_IDENTITY."""
    r = create_identity(uuid_a)
    email = r["email"]
    body = b"identifier=" + email.encode()
    resp = _make_request("/recover", method="POST", body=body, client_id="")
    assert resp.startswith(b"REDIRECT:/mail")
    assert b"SET_IDENTITY:" in resp
    assert uuid_a.encode() in resp


def test_recover_unknown_identifier(temp_db):
    """POST /recover mit unbekannter UUID -> Fehlerseite."""
    body = b"identifier=00000000-0000-0000-0000-000000000000"
    resp = _make_request("/recover", method="POST", body=body, client_id="")
    text = resp.decode("utf-8", "replace")
    assert "Keine Identitaet" in text
    assert not resp.startswith(b"REDIRECT:")


def test_recover_empty_identifier(temp_db):
    """POST /recover ohne identifier -> Fehlerseite."""
    resp = _make_request("/recover", method="POST", body=b"identifier=", client_id="")
    text = resp.decode("utf-8", "replace")
    assert "Fehler" in text or "Bitte" in text


def test_recover_identity_uuid_used(temp_db, uuid_a):
    """Mit identity_uuid: /mail nutzt die wiederhergestellte UUID."""
    create_identity(uuid_a)
    # GET /mail mit identity_uuid sollte die UUID nutzen
    from erebos_network.landing_pages import render_page
    html = render_page(
        path="/mail", address="test.erebos",
        request_line="GET /mail HTTP/1.1", method="GET", body=b"",
        query="", client_id="new-client-without-identity",
        identity_uuid=uuid_a,
    )
    text = html.decode("utf-8", "replace")
    assert uuid_a[:8] in text
