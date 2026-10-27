"""Tests fuer Chat-Persistenz, Rate-Limiting, Room-TTL."""

import time

import pytest


@pytest.fixture
def fresh_chat(temp_db, monkeypatch):
    """Frische Chat-Tabellen (temp_db + reset)."""
    from erebos_network import chat
    chat.reset()
    yield chat
    chat.reset()


def test_create_and_join_room(fresh_chat):
    room_id = fresh_chat.create_room()
    assert len(room_id) == 8
    assert fresh_chat.room_exists(room_id)
    assert fresh_chat.join_room(room_id, "cookie-A")
    assert fresh_chat.current_room("cookie-A") == room_id


def test_messages_persist_in_db(fresh_chat, temp_db, monkeypatch):
    from erebos_network import forum_db

    room_id = fresh_chat.create_room()
    fresh_chat.join_room(room_id, "cookie-A")
    ok, reason = fresh_chat.send_message(room_id, "cookie-A", "Hallo")
    assert ok, reason

    # Neue Verbindung simulieren (DB-Reset)
    monkeypatch.setattr(forum_db, "_conn", None)

    msgs = fresh_chat.get_messages(room_id, since=0)
    assert len(msgs) == 1
    assert msgs[0]["text"] == "Hallo"
    assert msgs[0]["from"] == "cookie-A"


def test_random_match(fresh_chat):
    r1 = fresh_chat.random_match("cookie-A")
    assert r1 == {"waiting": True}

    r2 = fresh_chat.random_match("cookie-B")
    assert "matched" in r2
    room_id = r2["matched"]

    # A ist auch gematcht
    assert fresh_chat.random_match("cookie-A") == {"matched": room_id}


def test_rate_limit_cookie(fresh_chat):
    room_id = fresh_chat.create_room()
    fresh_chat.join_room(room_id, "cookie-A")

    # Max 20 Nachrichten/Minute
    for i in range(fresh_chat.MAX_MSGS_PER_MINUTE_PER_COOKIE):
        ok, reason = fresh_chat.send_message(room_id, "cookie-A", f"msg {i}")
        assert ok, reason

    ok, reason = fresh_chat.send_message(room_id, "cookie-A", "overflow")
    assert not ok
    assert reason.startswith("rate_limit:")


def test_rate_limit_resets_after_window(fresh_chat, monkeypatch):
    room_id = fresh_chat.create_room()
    fresh_chat.join_room(room_id, "cookie-A")

    # Fülle Limit
    for i in range(fresh_chat.MAX_MSGS_PER_MINUTE_PER_COOKIE):
        fresh_chat.send_message(room_id, "cookie-A", f"msg {i}")

    ok, reason = fresh_chat.send_message(room_id, "cookie-A", "overflow")
    assert not ok

    # Zeit vorspulen (61s)
    original_now = fresh_chat._now
    monkeypatch.setattr(fresh_chat, "_now", lambda: original_now() + 61)

    ok, reason = fresh_chat.send_message(room_id, "cookie-A", "after window")
    assert ok, reason


def test_room_ttl_cleanup(fresh_chat, monkeypatch):
    room_id = fresh_chat.create_room()
    fresh_chat.join_room(room_id, "cookie-A")
    fresh_chat.send_message(room_id, "cookie-A", "Hallo")

    # Zeit vorspulen: 2 Stunden
    original_now = fresh_chat._now
    monkeypatch.setattr(fresh_chat, "_now", lambda: original_now() + 7200)

    n = fresh_chat.cleanup_old_rooms()
    assert n == 1
    assert not fresh_chat.room_exists(room_id)


def test_lazy_cleanup_on_create(fresh_chat, monkeypatch):
    old_room = fresh_chat.create_room()
    # 2h später: neuer Raum wird erstellt -> Cleanup
    original_now = fresh_chat._now
    monkeypatch.setattr(fresh_chat, "_now", lambda: original_now() + 7200)

    new_room = fresh_chat.create_room()
    assert not fresh_chat.room_exists(old_room)
    assert fresh_chat.room_exists(new_room)


def test_empty_message_rejected(fresh_chat):
    room_id = fresh_chat.create_room()
    ok, reason = fresh_chat.send_message(room_id, "cookie-A", "   ")
    assert not ok
    assert reason == "empty"


def test_message_nonexistent_room(fresh_chat):
    ok, reason = fresh_chat.send_message("nonexistent", "cookie-A", "Hallo")
    assert not ok
    assert reason == "room_not_found"
