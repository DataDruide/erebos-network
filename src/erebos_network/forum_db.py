"""SQLite-Backend fuer das Erebos-Forum.

Ersetzt die JSON-Datei durch eine SQLite-Datenbank. Die API bleibt
gleich: load_forum() / save_forum() in forum.py rufen intern diese
Funktionen auf.

Schema:
- threads: id, category_id, title, author, created_at, last_activity,
  sticky, locked, posts (JSON-Array).
- users: username, password_hash, salt, created_at.
- sessions: token, username, created_at, expires_at.
- admin_sessions: token, created_at, expires_at, client_id.
- reports: id, thread_id, post_index, reason, reporter, created_at, resolved.
- bans: id, username, reason, created_at.
- mod_log: id, action, target, moderator, created_at.
- login_failures: client_id, timestamp.
- categories: id, name, description.
"""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("/app/forum.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    category_id TEXT NOT NULL DEFAULT 'allgemein',
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_activity REAL,
    sticky INTEGER DEFAULT 0,
    locked INTEGER DEFAULT 0,
    posts TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    token TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    client_id TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    post_index INTEGER NOT NULL,
    reason TEXT,
    reporter TEXT,
    created_at REAL NOT NULL,
    resolved INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    reason TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS mod_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    moderator TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS login_failures (
    client_id TEXT NOT NULL,
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_threads_category ON threads(category_id);
CREATE INDEX IF NOT EXISTS idx_threads_created ON threads(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username);
CREATE INDEX IF NOT EXISTS idx_login_failures_client ON login_failures(client_id);
"""

_conn: Optional[sqlite3.Connection] = None


def get_db() -> sqlite3.Connection:
    """Liefert die (einmalige) SQLite-Verbindung."""
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        # DELETE-Modus statt WAL: WAL funktioniert nicht mit Docker-
        # Bind-Mounts (die WAL-Datei wird nicht synchronisiert).
        _conn.execute("PRAGMA journal_mode=DELETE")
        _conn.execute("PRAGMA foreign_keys=ON")
        # Sofort nach jedem Schreiben auf Platte (kein Buffering)
        _conn.execute("PRAGMA synchronous=FULL")
        _conn.executescript(SCHEMA)
        _conn.commit()
        logger.info(f"SQLite-DB initialisiert: {DB_PATH}")
    return _conn


def load_forum_from_db() -> dict:
    """Laedt alle Tabellen in ein Dict (gleiche Struktur wie forum.json)."""
    conn = get_db()
    data = {
        "threads": [],
        "users": {},
        "sessions": {},
        "admin_sessions": {},
        "reports": [],
        "bans": [],
        "mod_log": [],
        "login_failures": {},
        "categories": [],
    }

    # Threads
    for row in conn.execute(
        "SELECT id, category_id, title, author, created_at, last_activity, "
        "sticky, locked, posts FROM threads"
    ):
        data["threads"].append({
            "id": row[0],
            "category_id": row[1],
            "title": row[2],
            "author": row[3],
            "created_at": row[4],
            "last_activity": row[5] if row[5] is not None else row[4],
            "sticky": bool(row[6]),
            "locked": bool(row[7]),
            "posts": json.loads(row[8]) if row[8] else [],
        })

    # Users
    for row in conn.execute(
        "SELECT username, password_hash, salt, created_at FROM users"
    ):
        data["users"][row[0]] = {
            "username": row[0],
            "password_hash": row[1],
            "salt": row[2],
            "created_at": row[3],
        }

    # Sessions
    for row in conn.execute(
        "SELECT token, username, created_at, expires_at FROM sessions"
    ):
        data["sessions"][row[0]] = {
            "username": row[1],
            "created_at": row[2],
            "expires_at": row[3],
        }

    # Admin-Sessions
    for row in conn.execute(
        "SELECT token, created_at, expires_at, client_id FROM admin_sessions"
    ):
        data["admin_sessions"][row[0]] = {
            "created_at": row[1],
            "expires_at": row[2],
            "client_id": row[3] or "",
        }

    # Reports
    for row in conn.execute(
        "SELECT thread_id, post_index, reason, reporter, created_at, resolved "
        "FROM reports ORDER BY id"
    ):
        data["reports"].append({
            "thread_id": row[0],
            "post_index": row[1],
            "reason": row[2],
            "reporter": row[3],
            "created_at": row[4],
            "resolved": bool(row[5]),
        })

    # Bans
    for row in conn.execute(
        "SELECT username, reason, created_at FROM bans ORDER BY id"
    ):
        data["bans"].append({
            "username": row[0],
            "reason": row[1],
            "created_at": row[2],
        })

    # Mod-Log
    for row in conn.execute(
        "SELECT action, target, moderator, created_at FROM mod_log ORDER BY id"
    ):
        data["mod_log"].append({
            "action": row[0],
            "target": row[1],
            "moderator": row[2],
            "created_at": row[3],
        })

    # Login-Failures
    for row in conn.execute(
        "SELECT client_id, timestamp FROM login_failures"
    ):
        data["login_failures"].setdefault(row[0], []).append(row[1])

    # Categories
    for row in conn.execute(
        "SELECT id, name, description FROM categories ORDER BY id"
    ):
        data["categories"].append({
            "id": row[0],
            "name": row[1],
            "desc": row[2] or "",
        })

    return data


def save_forum_to_db(data: dict) -> bool:
    """Schreibt das Forum-Dict in einer Transaktion nach SQLite."""
    conn = get_db()
    try:
        with conn:  # Transaktion
            # Threads: alles loeschen und neu schreiben (Phase 1)
            conn.execute("DELETE FROM threads")
            for t in data.get("threads", []):
                conn.execute(
                    "INSERT INTO threads (id, category_id, title, author, "
                    "created_at, last_activity, sticky, locked, posts) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        t["id"],
                        t.get("category_id", "allgemein"),
                        t["title"],
                        t["author"],
                        t["created_at"],
                        t.get("last_activity", t["created_at"]),
                        1 if t.get("sticky") else 0,
                        1 if t.get("locked") else 0,
                        json.dumps(t.get("posts", [])),
                    ),
                )

            # Users
            conn.execute("DELETE FROM users")
            for username, u in data.get("users", {}).items():
                conn.execute(
                    "INSERT INTO users (username, password_hash, salt, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (username, u["password_hash"], u["salt"], u["created_at"]),
                )

            # Sessions
            conn.execute("DELETE FROM sessions")
            for token, s in data.get("sessions", {}).items():
                conn.execute(
                    "INSERT INTO sessions (token, username, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?)",
                    (token, s["username"], s["created_at"], s["expires_at"]),
                )

            # Admin-Sessions
            conn.execute("DELETE FROM admin_sessions")
            for token, s in data.get("admin_sessions", {}).items():
                conn.execute(
                    "INSERT INTO admin_sessions (token, created_at, expires_at, client_id) "
                    "VALUES (?, ?, ?, ?)",
                    (token, s["created_at"], s["expires_at"], s.get("client_id", "")),
                )

            # Reports
            conn.execute("DELETE FROM reports")
            for r in data.get("reports", []):
                conn.execute(
                    "INSERT INTO reports (thread_id, post_index, reason, reporter, "
                    "created_at, resolved) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        r["thread_id"], r["post_index"], r.get("reason", ""),
                        r.get("reporter", ""), r["created_at"],
                        1 if r.get("resolved") else 0,
                    ),
                )

            # Bans
            conn.execute("DELETE FROM bans")
            for b in data.get("bans", []):
                conn.execute(
                    "INSERT INTO bans (username, reason, created_at) VALUES (?, ?, ?)",
                    (b["username"], b.get("reason", ""), b["created_at"]),
                )

            # Mod-Log
            conn.execute("DELETE FROM mod_log")
            for m in data.get("mod_log", []):
                conn.execute(
                    "INSERT INTO mod_log (action, target, moderator, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (m["action"], m["target"], m.get("moderator", "admin"), m["created_at"]),
                )

            # Login-Failures
            conn.execute("DELETE FROM login_failures")
            for client_id, timestamps in data.get("login_failures", {}).items():
                for ts in timestamps:
                    conn.execute(
                        "INSERT INTO login_failures (client_id, timestamp) VALUES (?, ?)",
                        (client_id, ts),
                    )

            # Categories
            conn.execute("DELETE FROM categories")
            for c in data.get("categories", []):
                conn.execute(
                    "INSERT INTO categories (id, name, description) VALUES (?, ?, ?)",
                    (c["id"], c["name"], c.get("desc", "")),
                )

        return True
    except Exception as e:
        logger.error(f"SQLite-Schreibfehler: {e}")
        return False


def migrate_from_json(json_path: Path) -> int:
    """Importiert eine alte forum.json in die SQLite-DB.

    Returns:
        Anzahl der importierten Threads (0 = keine Migration).
    """
    conn = get_db()
    # Nur migrieren, wenn DB leer ist
    count = conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
    if count > 0:
        return 0
    if not json_path.exists():
        return 0
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Migration: forum.json nicht lesbar: {e}")
        return 0
    # Standard-Kategorien ergaenzen, falls leer
    if not data.get("categories"):
        from .forum import DEFAULT_CATEGORIES
        data["categories"] = list(DEFAULT_CATEGORIES)
    if save_forum_to_db(data):
        n = len(data.get("threads", []))
        logger.info(f"Migration: {n} Threads aus {json_path} importiert")
        return n
    return 0
