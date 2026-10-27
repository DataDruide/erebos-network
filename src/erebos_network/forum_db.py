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
    created_at REAL NOT NULL,
    mail_uuid TEXT
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

CREATE TABLE IF NOT EXISTS mail_keys (
    uuid TEXT PRIMARY KEY,
    x25519_pub TEXT NOT NULL,
    mlkem_pub TEXT NOT NULL,
    x25519_priv TEXT NOT NULL,
    mlkem_priv TEXT NOT NULL,
    ed25519_pub TEXT,
    ed25519_priv TEXT,
    mldsa_pub TEXT,
    mldsa_priv TEXT,
    key_version INTEGER DEFAULT 1,
    valid_from REAL,
    valid_until REAL,
    revoked_at REAL,
    superseded_by TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS mail_key_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL,
    key_version INTEGER NOT NULL,
    x25519_pub TEXT NOT NULL,
    mlkem_pub TEXT NOT NULL,
    ed25519_pub TEXT,
    mldsa_pub TEXT,
    x25519_priv TEXT,
    mlkem_priv TEXT,
    ed25519_priv TEXT,
    mldsa_priv TEXT,
    valid_from REAL NOT NULL,
    valid_until REAL,
    revoked_at REAL,
    superseded_by TEXT,
    UNIQUE(uuid, key_version)
);

CREATE INDEX IF NOT EXISTS idx_keyhist_uuid ON mail_key_history(uuid, key_version);

CREATE TABLE IF NOT EXISTS rotate_rate_limit (
    uuid TEXT PRIMARY KEY,
    last_rotate REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS identities (
    uuid TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    forum_username TEXT UNIQUE,
    created_at REAL NOT NULL,
    onboarded_at REAL
);

CREATE INDEX IF NOT EXISTS idx_identities_email ON identities(email);

CREATE TABLE IF NOT EXISTS mailboxes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_uuid TEXT NOT NULL,
    sender_uuid TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at REAL NOT NULL,
    read INTEGER DEFAULT 0,
    encrypted INTEGER DEFAULT 0,
    x25519_pub TEXT,
    mlkem_ct TEXT,
    nonce TEXT,
    ciphertext TEXT,
    signature_ed25519 TEXT,
    signature_mldsa TEXT,
    signature_mldsa_pub TEXT,
    sender_verified INTEGER DEFAULT 0,
    sender_key_version INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_mailboxes_owner ON mailboxes(owner_uuid);
CREATE INDEX IF NOT EXISTS idx_threads_category ON threads(category_id);
CREATE INDEX IF NOT EXISTS idx_threads_created ON threads(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username);
CREATE INDEX IF NOT EXISTS idx_login_failures_client ON login_failures(client_id);
"""

_conn: Optional[sqlite3.Connection] = None


def get_db() -> sqlite3.Connection:
    """Liefert die (einmalige) SQLite-Verbindung.

    Das Schema wird IMMER angewendet (idempotent durch
    CREATE TABLE IF NOT EXISTS). So werden neue Tabellen auch
    dann angelegt, wenn die DB schon existiert.
    """
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
        logger.info(f"SQLite-DB initialisiert: {DB_PATH}")
    # SCHEMA IMMER anwenden (idempotent durch IF NOT EXISTS)
    _conn.executescript(SCHEMA)
    _conn.commit()
    # Migration: fehlende Spalten in bestehenden Tabellen hinzufuegen
    _migrate_mailboxes(_conn)
    _migrate_identities(_conn)
    _migrate_mail_keys(_conn)
    _migrate_mail_key_history(_conn)
    _migrate_incomplete_mail_keys(_conn)
    _backfill_key_history_privkeys(_conn)
    return _conn


def _migrate_mailboxes(conn: sqlite3.Connection) -> None:
    """Fuegt fehlende Spalten zur mailboxes-Tabelle hinzu (idempotent).

    CREATE TABLE IF NOT EXISTS legt eine Tabelle nur an, wenn sie
    fehlt. Wenn sie schon existiert (z.B. aus einer frueheren
    Version), fehlen die neuen Spalten. ALTER TABLE ADD COLUMN
    fuegt sie hinzu — ohne Datenverlust.
    """
    # Pruefe, welche Spalten existieren
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(mailboxes)")
    }
    # Neue Spalten (Name, Typ, Default)
    new_columns = [
        ("encrypted", "INTEGER", "0"),
        ("x25519_pub", "TEXT", "NULL"),
        ("mlkem_ct", "TEXT", "NULL"),
        ("nonce", "TEXT", "NULL"),
        ("ciphertext", "TEXT", "NULL"),
        ("signature_ed25519", "TEXT", "NULL"),
        ("signature_mldsa", "TEXT", "NULL"),
        ("signature_mldsa_pub", "TEXT", "NULL"),
        ("sender_verified", "INTEGER", "0"),
        ("sender_key_version", "INTEGER", "1"),
        ("recipient_key_version", "INTEGER", "1"),
        ("verified_at", "REAL", "NULL"),
    ]
    for name, typ, default in new_columns:
        if name not in existing:
            try:
                conn.execute(
                    f"ALTER TABLE mailboxes ADD COLUMN {name} {typ} DEFAULT {default}"
                )
                logger.info(f"mailboxes: Spalte '{name}' hinzugefuegt")
            except Exception as e:
                logger.warning(f"mailboxes: Spalte '{name}' konnte nicht hinzugefuegt werden: {e}")
    conn.commit()


def _migrate_identities(conn: sqlite3.Connection) -> None:
    """Legt identities-Tabelle an und ergaenzt users.mail_uuid."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS identities (
            uuid TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            forum_username TEXT UNIQUE,
            created_at REAL NOT NULL,
            onboarded_at REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_identities_email ON identities(email)")
    # users.mail_uuid nachziehen (falls die Tabelle existiert)
    existing_users = {
        row[1] for row in conn.execute("PRAGMA table_info(users)")
    }
    if existing_users and "mail_uuid" not in existing_users:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN mail_uuid TEXT")
            logger.info("users: Spalte 'mail_uuid' hinzugefuegt")
        except Exception as e:
            logger.warning(f"users.mail_uuid nicht hinzugefuegt: {e}")
    conn.commit()


def _migrate_mail_keys(conn: sqlite3.Connection) -> None:
    """Fuegt fehlende ed25519-Spalten zur mail_keys-Tabelle hinzu."""
    # mail_key_history anlegen (idempotent, auch auf bestehender DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mail_key_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL,
            key_version INTEGER NOT NULL,
            x25519_pub TEXT NOT NULL,
            mlkem_pub TEXT NOT NULL,
            ed25519_pub TEXT,
            mldsa_pub TEXT,
            valid_from REAL NOT NULL,
            valid_until REAL,
            revoked_at REAL,
            superseded_by TEXT,
            UNIQUE(uuid, key_version)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_keyhist_uuid "
                 "ON mail_key_history(uuid, key_version)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rotate_rate_limit ("
        "uuid TEXT PRIMARY KEY, last_rotate REAL NOT NULL)"
    )
    # Privkey-Spalten nachziehen (Ansatz B)
    hist_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(mail_key_history)")
    }
    for name, typ in [
        ("x25519_priv", "TEXT"),
        ("mlkem_priv", "TEXT"),
        ("ed25519_priv", "TEXT"),
        ("mldsa_priv", "TEXT"),
        ("valid_until", "REAL"),
    ]:
        if name not in hist_cols:
            try:
                conn.execute(f"ALTER TABLE mail_key_history ADD COLUMN {name} {typ}")
                logger.info(f"mail_key_history: Spalte '{name}' hinzugefuegt")
            except Exception as e:
                logger.warning(f"mail_key_history: '{name}' nicht hinzugefuegt: {e}")

    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(mail_keys)")
    }
    for name, typ in [
        ("ed25519_pub", "TEXT"),
        ("ed25519_priv", "TEXT"),
        ("mldsa_pub", "TEXT"),
        ("mldsa_priv", "TEXT"),
        ("key_version", "INTEGER"),
        ("valid_from", "REAL"),
        ("valid_until", "REAL"),
        ("revoked_at", "REAL"),
        ("superseded_by", "TEXT"),
    ]:
        if name not in existing:
            try:
                conn.execute(f"ALTER TABLE mail_keys ADD COLUMN {name} {typ}")
                logger.info(f"mail_keys: Spalte '{name}' hinzugefuegt")
            except Exception as e:
                logger.warning(f"mail_keys: Spalte '{name}' konnte nicht hinzugefuegt werden: {e}")
    conn.commit()


def _migrate_mail_key_history(conn: sqlite3.Connection) -> None:
    """Befuellt mail_keys mit key_version=1/valid_from=created_at und
    legt fuer jede vollstaendige Zeile einen History-Eintrag an.

    Idempotent: mehrfacher Aufruf aendert nichts.
    Ueberspringt Zeilen ohne ed25519_pub oder mldsa_pub (unvollstaendig).
    """
    # 1) key_version/valid_from/valid_until fuer alle Zeilen setzen, wo NULL
    conn.execute(
        "UPDATE mail_keys SET key_version = 1 WHERE key_version IS NULL"
    )
    conn.execute(
        "UPDATE mail_keys SET valid_from = created_at WHERE valid_from IS NULL"
    )
    # valid_until = valid_from + MAIL_KEY_VALIDITY_SECONDS (nur wenn NULL)
    try:
        from .config import MAIL_KEY_VALIDITY_SECONDS
        conn.execute(
            "UPDATE mail_keys SET valid_until = COALESCE(valid_from, created_at) + ? "
            "WHERE valid_until IS NULL",
            (MAIL_KEY_VALIDITY_SECONDS,),
        )
    except Exception as e:
        logger.warning(f"valid_until-Migration fehlgeschlagen: {e}")

    # 2) History-Eintraege fuer vollstaendige Zeilen anlegen
    rows = conn.execute(
        "SELECT uuid, key_version, x25519_pub, mlkem_pub, "
        "ed25519_pub, mldsa_pub, valid_from, revoked_at, superseded_by "
        "FROM mail_keys "
        "WHERE ed25519_pub IS NOT NULL AND mldsa_pub IS NOT NULL "
        "  AND ed25519_pub != '' AND mldsa_pub != ''"
    ).fetchall()

    inserted = 0
    for r in rows:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO mail_key_history "
                "(uuid, key_version, x25519_pub, mlkem_pub, "
                " ed25519_pub, mldsa_pub, valid_from, valid_until, "
                " revoked_at, superseded_by) "
                "SELECT ?, ?, ?, ?, ?, ?, ?, valid_until, ?, ? "
                "FROM mail_keys WHERE uuid = ? AND key_version = ?",
                (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8],
                 r[0], r[1]),
            )
            inserted += conn.total_changes - inserted  # grob, fuer Log
        except Exception as e:
            logger.warning(f"mail_key_history: Insert fuer {r[0][:8]} fehlgeschlagen: {e}")

    if inserted:
        logger.info(f"mail_key_history: {inserted} Eintraege migriert")
    conn.commit()


_migration_running = False


def _migrate_incomplete_mail_keys(conn: sqlite3.Connection) -> None:
    """Ruft get_or_create_mail_keys fuer alle UUIDs mit unvollstaendigen Keys auf.

    Idempotent. Reentrancy-Guard verhindert Endlosrekursion, weil
    get_or_create_mail_keys intern get_db() aufruft.
    """
    global _migration_running
    if _migration_running:
        return
    _migration_running = True
    try:
        rows = conn.execute(
            "SELECT uuid FROM mail_keys "
            "WHERE ed25519_pub IS NULL OR mldsa_pub IS NULL "
            "   OR ed25519_priv IS NULL OR mldsa_priv IS NULL"
        ).fetchall()
        for (uuid,) in rows:
            try:
                get_or_create_mail_keys(uuid)
                logger.info(f"mail_keys: {uuid[:8]} nachgeneriert")
            except Exception as e:
                logger.warning(f"mail_keys: {uuid[:8]} Migration fehlgeschlagen: {e}")
    finally:
        _migration_running = False


def _backfill_key_history_privkeys(conn: sqlite3.Connection) -> None:
    """Stellt sicher, dass fuer jede vollstaendige mail_keys-Zeile ein
    History-Eintrag mit Privkeys existiert.

    - Wenn der History-Eintrag fehlt: INSERT (mit allen Pub+Privkeys).
    - Wenn er existiert: UPDATE der Privkeys (COALESCE, idempotent).

    Idempotent. Betrifft nur die AKTIVE Version (key_version ==
    mail_keys.key_version), weil aeltere Versionen keine Privkeys
    mehr in mail_keys haben.
    """
    rows = conn.execute(
        "SELECT m.uuid, m.key_version, m.x25519_pub, m.mlkem_pub, "
        "m.ed25519_pub, m.mldsa_pub, "
        "m.x25519_priv, m.mlkem_priv, m.ed25519_priv, m.mldsa_priv, "
        "COALESCE(m.valid_from, m.created_at) "
        "FROM mail_keys m "
        "WHERE m.ed25519_priv IS NOT NULL AND m.mldsa_priv IS NOT NULL"
    ).fetchall()
    inserted = 0
    updated = 0
    for r in rows:
        # Existiert schon ein History-Eintrag fuer diese (uuid, version)?
        exists = conn.execute(
            "SELECT 1 FROM mail_key_history WHERE uuid = ? AND key_version = ?",
            (r[0], r[1]),
        ).fetchone()

        if not exists:
            # INSERT: komplette Zeile (Pub + Priv + Valid_from)
            try:
                conn.execute(
                    "INSERT INTO mail_key_history "
                    "(uuid, key_version, x25519_pub, mlkem_pub, ed25519_pub, mldsa_pub, "
                    " x25519_priv, mlkem_priv, ed25519_priv, mldsa_priv, "
                    " valid_from, revoked_at, superseded_by) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                    (r[0], r[1], r[2], r[3], r[4], r[5],
                     r[6], r[7], r[8], r[9], r[10]),
                )
                inserted += 1
            except Exception as e:
                logger.warning(
                    f"mail_key_history: INSERT fuer {r[0][:8]} v{r[1]} "
                    f"fehlgeschlagen: {e}"
                )
        else:
            # UPDATE: nur die Privkeys (idempotent via COALESCE)
            conn.execute(
                "UPDATE mail_key_history SET "
                "x25519_priv = COALESCE(x25519_priv, ?), "
                "mlkem_priv = COALESCE(mlkem_priv, ?), "
                "ed25519_priv = COALESCE(ed25519_priv, ?), "
                "mldsa_priv = COALESCE(mldsa_priv, ?) "
                "WHERE uuid = ? AND key_version = ?",
                (r[6], r[7], r[8], r[9], r[0], r[1]),
            )
            updated += conn.total_changes

    if inserted:
        logger.info(f"mail_key_history: {inserted} Eintraege angelegt")
    if updated:
        logger.info(f"mail_key_history: {updated} Privkeys nachgetragen")
    conn.commit()


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


def set_mail_verified(mail_id: int, verified: int) -> None:
    """Persistiert den Verifikations-Status einer Mail.

    Args:
        mail_id: mailboxes.id
        verified: 0=nicht geprueft, 1=VERIFIED, 2=VERIFIED_OUTDATED,
                  3=VERIFY_FAILED

    Setzt zusaetzlich verified_at = now.
    """
    conn = get_db()
    with conn:
        conn.execute(
            "UPDATE mailboxes SET sender_verified = ?, verified_at = ? WHERE id = ?",
            (verified, time.time(), mail_id),
        )


def load_mails(owner_uuid: str, limit: int = 50) -> list:
    """Laedt die Mails eines Owners (neueste zuerst)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, sender_uuid, subject, body, created_at, read, "
        "encrypted, x25519_pub, mlkem_ct, nonce, ciphertext, "
        "signature_ed25519, signature_mldsa, signature_mldsa_pub, sender_verified, "
        "sender_key_version, recipient_key_version, verified_at "
        "FROM mailboxes WHERE owner_uuid = ? ORDER BY created_at DESC LIMIT ?",
        (owner_uuid, limit),
    ).fetchall()
    return [
        {
            "id": r[0],
            "sender_uuid": r[1],
            "subject": r[2],
            "body": r[3],
            "created_at": r[4],
            "read": bool(r[5]),
            "encrypted": bool(r[6]),
            "x25519_pub": r[7],
            "mlkem_ct": r[8],
            "nonce": r[9],
            "ciphertext": r[10],
            "signature_ed25519": r[11],
            "signature_mldsa": r[12],
            "signature_mldsa_pub": r[13],
            "sender_verified": int(r[14] or 0),
            "sender_key_version": r[15] or 1,
            "recipient_key_version": r[16] or 1,
            "verified_at": r[17],
        }
        for r in rows
    ]


def save_mail(owner_uuid: str, sender_uuid: str, subject: str, body: str,
              encrypted: bool = False, encrypted_fields: dict = None,
              signatures: dict = None, sender_verified: bool = False,
              sender_key_version: int = 1,
              recipient_key_version: int = 1) -> bool:
    """Speichert eine neue Mail (optional hybrid PQ-verschluesselt + signiert)."""
    conn = get_db()
    try:
        with conn:
            if encrypted and encrypted_fields:
                conn.execute(
                    "INSERT INTO mailboxes (owner_uuid, sender_uuid, subject, body, "
                    "created_at, encrypted, x25519_pub, mlkem_ct, nonce, ciphertext, "
                    "signature_ed25519, signature_mldsa, signature_mldsa_pub, sender_verified, "
                    "sender_key_version, recipient_key_version) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (owner_uuid, sender_uuid, subject, body, time.time(), 1,
                     encrypted_fields["x25519_pub"], encrypted_fields["mlkem_ct"],
                     encrypted_fields["nonce"], encrypted_fields["ciphertext"],
                     (signatures or {}).get("ed25519", ""),
                     (signatures or {}).get("mldsa", ""),
                     (signatures or {}).get("mldsa_pub", ""),
                     1 if sender_verified else 0,
                     sender_key_version, recipient_key_version),
                )
            else:
                conn.execute(
                    "INSERT INTO mailboxes (owner_uuid, sender_uuid, subject, body, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (owner_uuid, sender_uuid, subject, body, time.time()),
                )
        return True
    except Exception as e:
        logger.error(f"Mail konnte nicht gespeichert werden: {e}")
        return False


def mark_mail_read(mail_id: int) -> bool:
    """Markiert eine Mail als gelesen."""
    conn = get_db()
    try:
        with conn:
            conn.execute("UPDATE mailboxes SET read = 1 WHERE id = ?", (mail_id,))
        return True
    except Exception as e:
        logger.error(f"Mail konnte nicht als gelesen markiert werden: {e}")
        return False


def get_or_create_mail_keys(uuid: str) -> dict:
    """Laedt oder generiert die Mail-Schluessel eines Clients.

    Returns:
        dict mit x25519_pub, mlkem_pub, x25519_priv, mlkem_priv (hex).
    """
    import secrets as _secrets
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import oqs

    conn = get_db()
    row = conn.execute(
        "SELECT x25519_pub, mlkem_pub, x25519_priv, mlkem_priv, "
        "ed25519_pub, ed25519_priv, mldsa_pub, mldsa_priv, "
        "key_version, valid_from, valid_until, revoked_at, superseded_by "
        "FROM mail_keys WHERE uuid = ?",
        (uuid,),
    ).fetchone()
    if row and row[4] and row[5] and row[6] and row[7]:
        return {
            "x25519_pub": row[0],
            "mlkem_pub": row[1],
            "x25519_priv": row[2],
            "mlkem_priv": row[3],
            "ed25519_pub": row[4],
            "ed25519_priv": row[5],
            "mldsa_pub": row[6],
            "mldsa_priv": row[7],
            "key_version": row[8] or 1,
            "valid_from": row[9],
            "valid_until": row[10],
            "revoked_at": row[11],
            "superseded_by": row[12],
        }
    if row:
        # Alte Zeile ohne Ed25519/mldsa -> nachgenerieren
        import oqs
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        ed_pub_hex = row[4]
        ed_priv_hex = row[5]
        mldsa_pub_hex = row[6]
        mldsa_priv_hex = row[7]

        with conn:
            if not (ed_pub_hex and ed_priv_hex):
                ed_priv = Ed25519PrivateKey.generate()
                ed_pub = ed_priv.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
                ed_priv_raw = ed_priv.private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                )
                ed_pub_hex = ed_pub.hex()
                ed_priv_hex = ed_priv_raw.hex()
                conn.execute(
                    "UPDATE mail_keys SET ed25519_pub = ?, ed25519_priv = ? WHERE uuid = ?",
                    (ed_pub_hex, ed_priv_hex, uuid),
                )
            if not (mldsa_pub_hex and mldsa_priv_hex):
                mldsa = oqs.Signature("ML-DSA-65")
                mldsa_pub = mldsa.generate_keypair()  # Rueckgabe = Pubkey
                mldsa_priv_hex = mldsa.export_secret_key().hex()
                mldsa_pub_hex = mldsa_pub.hex()
                conn.execute(
                    "UPDATE mail_keys SET mldsa_pub = ?, mldsa_priv = ? WHERE uuid = ?",
                    (mldsa_pub_hex, mldsa_priv_hex, uuid),
                )

        return {
            "x25519_pub": row[0],
            "mlkem_pub": row[1],
            "x25519_priv": row[2],
            "mlkem_priv": row[3],
            "ed25519_pub": ed_pub_hex,
            "ed25519_priv": ed_priv_hex,
            "mldsa_pub": mldsa_pub_hex,
            "mldsa_priv": mldsa_priv_hex,
            "key_version": row[8] or 1,
            "valid_from": row[9],
            "valid_until": row[10],
            "revoked_at": row[11],
            "superseded_by": row[12],
        }

    # Neu generieren (X25519 + ML-KEM + Ed25519 + ML-DSA)
    import oqs
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    ed_priv = Ed25519PrivateKey.generate()
    ed_pub = ed_priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    ed_priv_raw = ed_priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    mldsa = oqs.Signature("ML-DSA-65")
    mldsa_pub = mldsa.generate_keypair()
    mldsa_priv_raw = mldsa.export_secret_key()
    x_priv = X25519PrivateKey.generate()
    x_pub = x_priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    x_priv_raw = x_priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    mlkem = oqs.KeyEncapsulation("ML-KEM-1024")
    mlkem_pub = mlkem.generate_keypair()
    mlkem_priv = mlkem.export_secret_key()

    from .config import MAIL_KEY_VALIDITY_SECONDS
    now = time.time()
    valid_until = now + MAIL_KEY_VALIDITY_SECONDS
    keys = {
        "x25519_pub": x_pub.hex(),
        "mlkem_pub": mlkem_pub.hex(),
        "x25519_priv": x_priv_raw.hex(),
        "mlkem_priv": mlkem_priv.hex(),
        "ed25519_pub": ed_pub.hex(),
        "ed25519_priv": ed_priv_raw.hex(),
        "mldsa_pub": mldsa_pub.hex(),
        "mldsa_priv": mldsa_priv_raw.hex(),
        "key_version": 1,
        "valid_from": now,
        "valid_until": valid_until,
        "revoked_at": None,
        "superseded_by": None,
    }
    with conn:
        conn.execute(
            "INSERT INTO mail_keys (uuid, x25519_pub, mlkem_pub, x25519_priv, mlkem_priv, "
            "ed25519_pub, ed25519_priv, mldsa_pub, mldsa_priv, "
            "key_version, valid_from, valid_until, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uuid, keys["x25519_pub"], keys["mlkem_pub"],
             keys["x25519_priv"], keys["mlkem_priv"],
             keys["ed25519_pub"], keys["ed25519_priv"],
             keys["mldsa_pub"], keys["mldsa_priv"],
             keys["key_version"], keys["valid_from"], keys["valid_until"], now),
        )
    logger.info(f"Mail-Schluessel generiert fuer #{uuid[:8]}")
    return keys


def rotate_mail_keys(uuid: str) -> dict:
    """Erzeugt einen neuen Key-Satz fuer uuid (Key-Rotation).

    Nutzt exakt dieselbe Krypto-API wie get_or_create_mail_keys:
        - X25519: cryptography.hazmat
        - ML-KEM-1024: oqs.KeyEncapsulation("ML-KEM-1024")
        - Ed25519: cryptography.hazmat
        - ML-DSA-65: oqs.Signature("ML-DSA-65")

    Der alte Satz bleibt in mail_key_history erhalten (fuer Verify alter
    Mails), wird aber als revoked markiert:
        revoked_at = now, superseded_by = "v(N+1)".

    Returns:
        dict mit den NEUEN Keys (gleiche Felder wie get_or_create_mail_keys)

    Raises:
        ValueError: wenn uuid keine aktiven mail_keys hat
    """
    import oqs
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    conn = get_db()
    row = conn.execute(
        "SELECT key_version FROM mail_keys WHERE uuid = ?",
        (uuid,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Keine mail_keys fuer uuid={uuid[:8]}")

    old_version = row[0] or 1
    new_version = old_version + 1
    now = time.time()

    # --- Neuen Key-Satz erzeugen (identisch zu get_or_create_mail_keys) ---
    x_priv = X25519PrivateKey.generate()
    x_pub = x_priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    x_priv_raw = x_priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )

    mlkem = oqs.KeyEncapsulation("ML-KEM-1024")
    mlkem_pub = mlkem.generate_keypair()
    mlkem_priv = mlkem.export_secret_key()

    ed_priv = Ed25519PrivateKey.generate()
    ed_pub = ed_priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    ed_priv_raw = ed_priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )

    mldsa = oqs.Signature("ML-DSA-65")
    mldsa_pub = mldsa.generate_keypair()
    mldsa_priv_raw = mldsa.export_secret_key()

    from .config import MAIL_KEY_VALIDITY_SECONDS
    valid_until = now + MAIL_KEY_VALIDITY_SECONDS
    keys = {
        "x25519_pub": x_pub.hex(),
        "mlkem_pub": mlkem_pub.hex(),
        "x25519_priv": x_priv_raw.hex(),
        "mlkem_priv": mlkem_priv.hex(),
        "ed25519_pub": ed_pub.hex(),
        "ed25519_priv": ed_priv_raw.hex(),
        "mldsa_pub": mldsa_pub.hex(),
        "mldsa_priv": mldsa_priv_raw.hex(),
        "key_version": new_version,
        "valid_from": now,
        "valid_until": valid_until,
        "revoked_at": None,
        "superseded_by": None,
    }

    with conn:
        # 1) Alte Version in History als revoked markieren
        conn.execute(
            "UPDATE mail_key_history SET revoked_at = ?, superseded_by = ? "
            "WHERE uuid = ? AND key_version = ?",
            (now, f"v{new_version}", uuid, old_version),
        )
        # 2) Neuen Satz in mail_keys eintragen
        conn.execute(
            "UPDATE mail_keys SET "
            "x25519_pub = ?, mlkem_pub = ?, x25519_priv = ?, mlkem_priv = ?, "
            "ed25519_pub = ?, ed25519_priv = ?, mldsa_pub = ?, mldsa_priv = ?, "
            "key_version = ?, valid_from = ?, valid_until = ?, "
            "revoked_at = NULL, superseded_by = NULL "
            "WHERE uuid = ?",
            (keys["x25519_pub"], keys["mlkem_pub"],
             keys["x25519_priv"], keys["mlkem_priv"],
             keys["ed25519_pub"], keys["ed25519_priv"],
             keys["mldsa_pub"], keys["mldsa_priv"],
             new_version, now, valid_until, uuid),
        )
        # 3) Neue Version in History als aktiv eintragen
        conn.execute(
            "INSERT INTO mail_key_history "
            "(uuid, key_version, x25519_pub, mlkem_pub, ed25519_pub, mldsa_pub, "
            "valid_from, revoked_at, superseded_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
            (uuid, new_version, keys["x25519_pub"], keys["mlkem_pub"],
             keys["ed25519_pub"], keys["mldsa_pub"], now),
        )

    logger.info(f"mail_keys rotiert: uuid={uuid[:8]} v{old_version} -> v{new_version}")
    return keys


def get_mail_keys_by_version(uuid: str, key_version: int) -> dict:
    """Laedt einen bestimmten Key-Satz aus mail_key_history (inkl. Privkeys).

    Wird bei Ansatz B genutzt, um alte Mails zu entschluesseln, die mit
    einer aelteren Empfaenger-Version verschluesselt wurden.

    Returns:
        dict mit x25519_pub, mlkem_pub, ed25519_pub, mldsa_pub,
        x25519_priv, mlkem_priv, ed25519_priv, mldsa_priv,
        valid_from, revoked_at, superseded_by; oder None wenn nicht
        vorhanden.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT x25519_pub, mlkem_pub, ed25519_pub, mldsa_pub, "
        "x25519_priv, mlkem_priv, ed25519_priv, mldsa_priv, "
        "valid_from, valid_until, revoked_at, superseded_by "
        "FROM mail_key_history WHERE uuid = ? AND key_version = ?",
        (uuid, key_version),
    ).fetchone()
    if row is None:
        return None
    return {
        "x25519_pub": row[0],
        "mlkem_pub": row[1],
        "ed25519_pub": row[2],
        "mldsa_pub": row[3],
        "x25519_priv": row[4],
        "mlkem_priv": row[5],
        "ed25519_priv": row[6],
        "mldsa_priv": row[7],
        "valid_from": row[8],
        "valid_until": row[9],
        "revoked_at": row[10],
        "superseded_by": row[11],
        "key_version": key_version,
    }


def find_expiring_keys(days_before: float = None) -> list:
    """Findet mail_keys, die in den naechsten `days_before` Tagen ablaufen.

    Returns:
        Liste von dicts mit uuid, key_version, valid_until, days_left.
    """
    import time as _time
    from .config import ROTATE_BEFORE_EXPIRY_DAYS

    if days_before is None:
        days_before = ROTATE_BEFORE_EXPIRY_DAYS

    now = _time.time()
    threshold = now + days_before * 86400
    conn = get_db()
    rows = conn.execute(
        "SELECT uuid, key_version, valid_until "
        "FROM mail_keys "
        "WHERE valid_until IS NOT NULL "
        "  AND valid_until <= ? "
        "ORDER BY valid_until ASC",
        (threshold,),
    ).fetchall()
    return [
        {
            "uuid": r[0],
            "key_version": r[1],
            "valid_until": r[2],
            "days_left": (r[2] - now) / 86400 if r[2] else None,
        }
        for r in rows
    ]


def auto_rotate_expiring_keys(days_before: float = None,
                             dry_run: bool = False) -> dict:
    """Rotiert alle Keys, die in den naechsten `days_before` Tagen ablaufen.

    Umgeht das Rate-Limit (die Rotation ist legitim, weil der Key
    wirklich abläuft). Loggt jede Rotation.

    Args:
        days_before: Schwellwert in Tagen (Default aus config).
        dry_run:     Wenn True, nur auflisten, nicht rotieren.

    Returns:
        dict mit rotated (list), failed (list), skipped (list)
    """
    expiring = find_expiring_keys(days_before)
    result = {"rotated": [], "failed": [], "skipped": []}

    if not expiring:
        logger.info("auto_rotate: keine ablaufenden Keys gefunden")
        return result

    logger.info(
        f"auto_rotate: {len(expiring)} Keys laufen bald ab — starte Rotation"
    )

    for entry in expiring:
        uuid = entry["uuid"]
        old_version = entry["key_version"]
        days_left = entry["days_left"]
        if dry_run:
            logger.info(
                f"auto_rotate (dry-run): wuerde {uuid[:8]} v{old_version} "
                f"rotieren (laeuft in {days_left:.1f} Tagen ab)"
            )
            result["skipped"].append(uuid)
            continue
        try:
            new_keys = rotate_mail_keys(uuid)
            logger.info(
                f"auto_rotate: {uuid[:8]} v{old_version} -> "
                f"v{new_keys['key_version']} (lief in {days_left:.1f} Tagen ab)"
            )
            result["rotated"].append(uuid)
        except Exception as e:
            logger.error(f"auto_rotate: {uuid[:8]} fehlgeschlagen: {e}")
            result["failed"].append((uuid, str(e)))

    return result


def create_identity(uuid: str) -> dict:
    """Erstellt eine Identitaet fuer die UUID.

    - Erzeugt E-Mail-Adresse `<kurzform>@erebos`
    - Erzeugt Forum-Username `erebos_<kurzform>` (falls nicht vorhanden)
    - Ruft get_or_create_mail_keys auf (Mail-Postfach)
    - Markiert Identitaet als onboarded

    Idempotent: mehrfacher Aufruf aendert nichts.

    Returns:
        dict mit uuid, email, forum_username, mail_keys, forum_user
    """
    import secrets as _secrets
    import hashlib as _hashlib
    import time as _time

    conn = get_db()
    short = uuid.replace("-", "")[:8]
    email = f"{short}@erebos"
    forum_username = f"erebos_{short}"

    # 1) Identity-Zeile anlegen (oder bestehende nutzen)
    row = conn.execute(
        "SELECT email, forum_username, onboarded_at FROM identities WHERE uuid = ?",
        (uuid,),
    ).fetchone()
    if row is None:
        with conn:
            conn.execute(
                "INSERT INTO identities (uuid, email, forum_username, created_at) "
                "VALUES (?, ?, ?, ?)",
                (uuid, email, forum_username, _time.time()),
            )
        email = email
        forum_username = forum_username
    else:
        email, forum_username, _onboarded = row

    # 2) Mail-Keys sicherstellen (idempotent)
    mail_keys = get_or_create_mail_keys(uuid)

    # 3) Forum-User sicherstellen (falls nicht vorhanden)
    forum_user = None
    existing = conn.execute(
        "SELECT username FROM users WHERE username = ?",
        (forum_username,),
    ).fetchone()
    if existing is None:
        # Zufaelliges Passwort generieren (User kann es aendern)
        pw = _secrets.token_urlsafe(24)
        salt = _secrets.token_hex(16)
        pw_hash = _hashlib.sha256((salt + pw).encode("utf-8")).hexdigest()
        with conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, created_at, mail_uuid) "
                "VALUES (?, ?, ?, ?, ?)",
                (forum_username, pw_hash, salt, _time.time(), uuid),
            )
        forum_user = {
            "username": forum_username,
            "password": pw,  # einmalig zurueckgeben
        }
        logger.info(f"Identity: Forum-User '{forum_username}' fuer {uuid[:8]}")
    else:
        forum_user = {"username": forum_username, "password": None}

    # 4) onboarded_at setzen
    with conn:
        conn.execute(
            "UPDATE identities SET onboarded_at = ? WHERE uuid = ?",
            (_time.time(), uuid),
        )

    return {
        "uuid": uuid,
        "email": email,
        "forum_username": forum_username,
        "mail_keys": mail_keys,
        "forum_user": forum_user,
    }


def get_identity(uuid: str) -> dict:
    """Laedt eine Identitaet (oder None)."""
    conn = get_db()
    row = conn.execute(
        "SELECT uuid, email, forum_username, created_at, onboarded_at "
        "FROM identities WHERE uuid = ?",
        (uuid,),
    ).fetchone()
    if row is None:
        return None
    return {
        "uuid": row[0],
        "email": row[1],
        "forum_username": row[2],
        "created_at": row[3],
        "onboarded_at": row[4],
    }


def get_or_create_forum_session(mail_uuid: str) -> dict:
    """Erzeugt (oder laedt) eine Forum-Session fuer die Mail-UUID.

    Wird beim Auto-Login nach Onboarding genutzt.

    Returns:
        dict mit token, username, expires_at; oder None wenn keine Identity.
    """
    import secrets as _secrets
    import time as _time

    conn = get_db()
    ident = conn.execute(
        "SELECT forum_username FROM identities WHERE uuid = ?",
        (mail_uuid,),
    ).fetchone()
    if ident is None or not ident[0]:
        return None
    username = ident[0]

    # Existierende Session?
    now = _time.time()
    existing = conn.execute(
        "SELECT token, expires_at FROM sessions "
        "WHERE username = ? AND expires_at > ? "
        "ORDER BY created_at DESC LIMIT 1",
        (username, now),
    ).fetchone()
    if existing:
        return {
            "token": existing[0],
            "username": username,
            "expires_at": existing[1],
        }

    # Neue Session erzeugen
    token = _secrets.token_urlsafe(32)
    expires_at = now + 7 * 86400  # 7 Tage
    with conn:
        conn.execute(
            "INSERT INTO sessions (token, username, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token, username, now, expires_at),
        )
    return {
        "token": token,
        "username": username,
        "expires_at": expires_at,
    }


def find_identity_by_identifier(identifier: str) -> dict:
    """Sucht eine Identitaet anhand UUID oder E-Mail.

    Args:
        identifier: UUID (mit oder ohne Bindestriche) ODER E-Mail (<kurzform>@erebos).

    Returns:
        dict mit uuid, email, forum_username, onboarded_at; oder None.
    """
    if not identifier:
        return None
    ident = identifier.strip()

    conn = get_db()

    # Erst UUID (mit Bindestrichen)
    row = conn.execute(
        "SELECT uuid, email, forum_username, onboarded_at FROM identities WHERE uuid = ?",
        (ident,),
    ).fetchone()

    # Dann E-Mail
    if row is None:
        row = conn.execute(
            "SELECT uuid, email, forum_username, onboarded_at FROM identities WHERE email = ?",
            (ident,),
        ).fetchone()

    # Dann UUID ohne Bindestriche (Kurzform)
    if row is None and len(ident) == 8:
        row = conn.execute(
            "SELECT uuid, email, forum_username, onboarded_at FROM identities "
            "WHERE uuid LIKE ?",
            (ident + "%",),
        ).fetchone()

    if row is None:
        return None
    return {
        "uuid": row[0],
        "email": row[1],
        "forum_username": row[2],
        "onboarded_at": row[3],
    }


def check_rotate_rate_limit(uuid: str) -> tuple:
    """Prueft, ob eine Rotation fuer uuid erlaubt ist.

    Returns:
        (allowed: bool, retry_after: float)
    """
    from .config import ROTATE_RATE_LIMIT_SECONDS
    import time as _time

    conn = get_db()
    row = conn.execute(
        "SELECT last_rotate FROM rotate_rate_limit WHERE uuid = ?",
        (uuid,),
    ).fetchone()
    if row is None:
        return (True, 0.0)
    elapsed = _time.time() - row[0]
    if elapsed >= ROTATE_RATE_LIMIT_SECONDS:
        return (True, 0.0)
    return (False, ROTATE_RATE_LIMIT_SECONDS - elapsed)


def record_rotate(uuid: str) -> None:
    """Traegt den aktuellen Zeitpunkt als letzte Rotation ein.

    Loescht ausserdem alte Eintraege (>24 h), um die Tabelle klein zu halten.
    """
    import time as _time
    conn = get_db()
    now = _time.time()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO rotate_rate_limit (uuid, last_rotate) "
            "VALUES (?, ?)",
            (uuid, now),
        )
        conn.execute(
            "DELETE FROM rotate_rate_limit WHERE last_rotate < ?",
            (now - 86400,),
        )


def get_mail_keys(uuid: str) -> dict:
    """Laedt die Mail-Schluessel eines Clients (oder None).

    Reine Lese-Variante — generiert KEINE Schluessel. Signatur-Spalten
    (ed25519, mldsa) koennen bei alten Zeilen None sein; der Aufrufer
    muss damit umgehen koennen.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT x25519_pub, mlkem_pub, x25519_priv, mlkem_priv, "
        "ed25519_pub, ed25519_priv, mldsa_pub, mldsa_priv, "
        "key_version, valid_from, valid_until, revoked_at, superseded_by "
        "FROM mail_keys WHERE uuid = ?",
        (uuid,),
    ).fetchone()
    if row is None:
        return None
    return {
        "x25519_pub": row[0],
        "mlkem_pub": row[1],
        "x25519_priv": row[2],
        "mlkem_priv": row[3],
        "ed25519_pub": row[4],
        "ed25519_priv": row[5],
        "mldsa_pub": row[6],
        "mldsa_priv": row[7],
        "key_version": row[8] or 1,
        "valid_from": row[9],
        "valid_until": row[10],
        "revoked_at": row[11],
        "superseded_by": row[12],
    }
