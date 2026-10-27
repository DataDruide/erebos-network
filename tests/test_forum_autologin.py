"""Tests fuer Forum-Auto-Login nach Onboarding."""

import uuid as _uuid
from erebos_network.landing_pages import render_page
from erebos_network.forum_db import (
    create_identity, get_identity, get_or_create_forum_session,
)


def _client_id():
    return "test-client-forumautologin-001"


def _uuid_for(client_id):
    return str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))


def _make_request(path, client_id="", username=""):
    return render_page(
        path=path,
        address="test.erebos",
        request_line=f"GET {path} HTTP/1.1",
        method="GET",
        body=b"",
        query="",
        client_id=client_id,
        username=username,
    )


def test_get_or_create_forum_session_creates(temp_db, uuid_a):
    create_identity(uuid_a)
    session = get_or_create_forum_session(uuid_a)
    assert session is not None
    assert session["username"].startswith("erebos_")
    assert session["token"]


def test_get_or_create_forum_session_idempotent(temp_db, uuid_a):
    create_identity(uuid_a)
    s1 = get_or_create_forum_session(uuid_a)
    s2 = get_or_create_forum_session(uuid_a)
    assert s1["token"] == s2["token"]


def test_get_or_create_forum_session_missing_identity(temp_db):
    assert get_or_create_forum_session("00000000-0000-0000-0000-000000000000") is None


def test_forum_autologin_after_onboarding(temp_db):
    cid = _client_id()
    uuid = _uuid_for(cid)
    _make_request("/onboard", client_id=cid)
    ident = get_identity(uuid)
    assert ident is not None
    assert ident["onboarded_at"] is not None

    body = _make_request("/forum", client_id=cid, username="")
    assert body.startswith(b"REDIRECT:/forum"), f"Got {body[:80]!r}"
    assert b"SET_SESSION:" in body


def test_forum_no_autologin_without_onboarding(temp_db):
    cid = _client_id()
    body = _make_request("/forum", client_id=cid, username="")
    assert not body.startswith(b"REDIRECT:/forum")


def test_forum_no_autologin_if_logged_in(temp_db):
    cid = _client_id()
    _make_request("/onboard", client_id=cid)
    body = _make_request("/forum", client_id=cid, username="erebos_test")
    assert not body.startswith(b"REDIRECT:/forum")
