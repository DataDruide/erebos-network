"""Chat-State fuer Erebos Network (SQLite-persistent).

Verwaltet:
- Rooms (chat_rooms)
- Members (chat_members)
- Messages (chat_messages)
- Random-Queue (chat_random_queue)

Rate-Limiting: In-Memory (Sliding Window), kein DB-Overhead.
Room-TTL: Cleanup loescht Rooms, deren last_activity > TTL zurueckliegt.
"""

import os
import secrets
import sqlite3
import time
from typing import Optional

from .forum_db import get_db

# Konfiguration
ROOM_TTL_HOURS = 1.0
ROOM_TTL_SEC = ROOM_TTL_HOURS * 3600
CLEANUP_INTERVAL_SEC = 600  # 10 Minuten

MAX_MSGS_PER_MINUTE_PER_COOKIE = 20
MAX_MSGS_PER_MINUTE_PER_ROOM = 60
RATE_WINDOW_SEC = 60.0

# In-Memory Rate-Limit-Tracking
_RATE_COOKIE: dict[str, list[float]] = {}
_RATE_ROOM: dict[str, list[float]] = {}


# ---------------------------------------------------------------------------
# Interna
# ---------------------------------------------------------------------------

def _now() -> float:
    return time.time()


def _cleanup_old_rooms(conn: sqlite3.Connection) -> int:
    """Loescht Rooms, deren last_activity > TTL zurueckliegt. Gibt Anzahl zurueck."""
    cutoff = _now() - ROOM_TTL_SEC
    old = conn.execute(
        "SELECT id FROM chat_rooms WHERE last_activity < ?", (cutoff,)
    ).fetchall()
    if not old:
        return 0
    ids = [r[0] for r in old]
    placeholders = ",".join("?" * len(ids))
    with conn:
        # CASCADE loescht members + messages
        conn.execute(f"DELETE FROM chat_rooms WHERE id IN ({placeholders})", ids)
    return len(ids)


def _touch_room(conn: sqlite3.Connection, room_id: str) -> None:
    """Aktualisiert last_activity eines Raums."""
    conn.execute(
        "UPDATE chat_rooms SET last_activity = ? WHERE id = ?",
        (_now(), room_id),
    )


def _check_rate_limit(cookie: str, room_id: str) -> tuple[bool, int]:
    """Prueft Rate-Limit. Gibt (allowed, retry_after_sec) zurueck."""
    now = _now()
    cutoff = now - RATE_WINDOW_SEC

    # Cookie-Limit
    ts = [t for t in _RATE_COOKIE.get(cookie, []) if t > cutoff]
    if len(ts) >= MAX_MSGS_PER_MINUTE_PER_COOKIE:
        return False, int(RATE_WINDOW_SEC - (now - ts[0])) + 1
    ts.append(now)
    _RATE_COOKIE[cookie] = ts[-MAX_MSGS_PER_MINUTE_PER_COOKIE:]

    # Raum-Limit
    ts_r = [t for t in _RATE_ROOM.get(room_id, []) if t > cutoff]
    if len(ts_r) >= MAX_MSGS_PER_MINUTE_PER_ROOM:
        return False, int(RATE_WINDOW_SEC - (now - ts_r[0])) + 1
    ts_r.append(now)
    _RATE_ROOM[room_id] = ts_r[-MAX_MSGS_PER_MINUTE_PER_ROOM:]

    return True, 0


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

def create_room(random: bool = False) -> str:
    """Erzeugt einen neuen Raum, gibt room_id (8 Hex) zurueck."""
    conn = get_db()
    _cleanup_old_rooms(conn)  # Lazy-Cleanup
    room_id = secrets.token_hex(4)
    now = _now()
    with conn:
        conn.execute(
            "INSERT INTO chat_rooms (id, created_at, random, last_activity) "
            "VALUES (?, ?, ?, ?)",
            (room_id, now, 1 if random else 0, now),
        )
    return room_id


def room_exists(room_id: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM chat_rooms WHERE id = ?", (room_id,)
    ).fetchone()
    return row is not None


def join_room(room_id: str, cookie: str) -> bool:
    """Client tritt Raum bei. False, wenn Raum nicht existiert."""
    conn = get_db()
    if not room_exists(room_id):
        return False
    now = _now()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO chat_members (room_id, cookie, joined_at) "
            "VALUES (?, ?, ?)",
            (room_id, cookie, now),
        )
        _touch_room(conn, room_id)
    return True


def leave_room(cookie: str) -> None:
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM chat_members WHERE cookie = ?", (cookie,))


def current_room(cookie: str) -> Optional[str]:
    conn = get_db()
    row = conn.execute(
        "SELECT room_id FROM chat_members WHERE cookie = ? "
        "ORDER BY joined_at DESC LIMIT 1",
        (cookie,),
    ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def send_message(room_id: str, cookie: str, text: str) -> tuple[bool, str]:
    """Fuegt Nachricht hinzu.

    Returns:
        (True, "")                 -> gespeichert
        (False, "rate_limit:N")    -> Rate-Limit, N = retry_after_sec
        (False, "room_not_found")  -> Raum existiert nicht
        (False, "empty")           -> leere Nachricht
    """
    text = (text or "").strip()
    if not text:
        return False, "empty"
    if not room_exists(room_id):
        return False, "room_not_found"

    allowed, retry = _check_rate_limit(cookie, room_id)
    if not allowed:
        return False, f"rate_limit:{retry}"

    conn = get_db()
    now = _now()
    with conn:
        conn.execute(
            "INSERT INTO chat_messages (room_id, author_cookie, text, created_at) "
            "VALUES (?, ?, ?, ?)",
            (room_id, cookie, text[:2000], now),
        )
        _touch_room(conn, room_id)
    return True, ""


def get_messages(room_id: str, since: float = 0.0) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, author_cookie, text, created_at FROM chat_messages "
        "WHERE room_id = ? AND created_at > ? ORDER BY created_at ASC",
        (room_id, since),
    ).fetchall()
    return [
        {"id": r[0], "from": r[1], "text": r[2], "ts": r[3]}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Random-Matchmaking
# ---------------------------------------------------------------------------

def random_match(cookie: str) -> dict:
    """Matchmaking. Gibt {"matched": room_id} oder {"waiting": True} zurueck."""
    conn = get_db()
    _cleanup_old_rooms(conn)

    # Schon in einem Random-Raum?
    existing = current_room(cookie)
    if existing:
        row = conn.execute(
            "SELECT random FROM chat_rooms WHERE id = ?", (existing,)
        ).fetchone()
        if row and row[0]:
            return {"matched": existing}

    # Jemand wartet?
    now = _now()
    while True:
        partner_row = conn.execute(
            "SELECT cookie FROM chat_random_queue "
            "WHERE cookie != ? ORDER BY queued_at ASC LIMIT 1",
            (cookie,),
        ).fetchone()
        if not partner_row:
            break
        partner = partner_row[0]
        # Partner hat inzwischen einen Raum? -> aus Queue entfernen, weiter
        if current_room(partner):
            with conn:
                conn.execute(
                    "DELETE FROM chat_random_queue WHERE cookie = ?", (partner,)
                )
            continue
        # Match!
        room_id = create_room(random=True)
        join_room(room_id, cookie)
        join_room(room_id, partner)
        with conn:
            conn.execute(
                "DELETE FROM chat_random_queue WHERE cookie IN (?, ?)",
                (cookie, partner),
            )
        return {"matched": room_id}

    # In Queue
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO chat_random_queue (cookie, queued_at) "
            "VALUES (?, ?)",
            (cookie, now),
        )
    return {"waiting": True}


def random_status(cookie: str) -> dict:
    """Status fuer Polling: matched/waiting/idle."""
    conn = get_db()
    room_id = current_room(cookie)
    if room_id:
        row = conn.execute(
            "SELECT random FROM chat_rooms WHERE id = ?", (room_id,)
        ).fetchone()
        if row and row[0]:
            return {"matched": room_id}
    queued = conn.execute(
        "SELECT 1 FROM chat_random_queue WHERE cookie = ?", (cookie,)
    ).fetchone()
    if queued:
        return {"waiting": True}
    return {"idle": True}


# ---------------------------------------------------------------------------
# Cleanup (periodisch aufgerufen)
# ---------------------------------------------------------------------------

def cleanup_old_rooms() -> int:
    """Loescht Rooms > TTL. Gibt Anzahl zurueck. Fuer periodischen Task."""
    conn = get_db()
    return _cleanup_old_rooms(conn)


# ---------------------------------------------------------------------------
# Debug/Test
# ---------------------------------------------------------------------------

def reset() -> None:
    """Loescht alle Chat-Daten (nur fuer Tests)."""
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM chat_rooms")
        conn.execute("DELETE FROM chat_members")
        conn.execute("DELETE FROM chat_messages")
        conn.execute("DELETE FROM chat_random_queue")
    _RATE_COOKIE.clear()
    _RATE_ROOM.clear()
