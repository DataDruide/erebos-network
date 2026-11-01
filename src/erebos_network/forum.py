"""Einfaches Forum fuer den Erebos Hidden-Service (JSON-persistent)."""

import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Optional, Tuple

from .forum_db import (
    get_db as _get_db,
    load_forum_from_db as _load_from_db,
    save_forum_to_db as _save_to_db,
    migrate_from_json as _migrate_from_json,
    get_user_email,
    get_user_role,
    insert_mod_log,
)
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)

from .paths import app_file
FORUM_JSON_PATH = app_file("forum.json")  # nur fuer Migration
FORUM_PATH = FORUM_JSON_PATH  # Backward-Compat
MAX_TITLE = 200
MAX_AUTHOR = 60
MAX_BODY = 4000

# Rate-Limit pro Client (Cookie) und global.
RATE_WINDOW_SECONDS = 600       # 10 Minuten
RATE_MAX_THREADS = 10           # neue Threads pro Client/Fenster
RATE_MAX_REPLIES = 30           # Antworten pro Client/Fenster
GLOBAL_MAX_THREADS = 50         # Sicherheitsnetz global
GLOBAL_MAX_REPLIES = 150        # Sicherheitsnetz global
CLIENT_COOKIE = "forum_client_id"
SESSION_COOKIE = "forum_session"
ADMIN_COOKIE = "forum_admin"
IDENTITY_COOKIE = "forum_identity"
ADMIN_COOKIE_TTL_SECONDS = 3600  # 1 Stunde
PBKDF2_ITERATIONS = 200_000
MIN_PASSWORD_LEN = 8
MAX_USERNAME_LEN = 32
SESSION_TTL_SECONDS = 7 * 24 * 3600  # 7 Tage

# Login-Rate-Limit (gegen Brute-Force): max. 5 Fehlversuche pro
# Client-ID in 5 Minuten.
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_FAILURES = 5
# Globales Sicherheitsnetz: max. 50 Fehlversuche pro Fenster insgesamt.
# Verhindert Umgehung durch Cookie-Löschen (neue client_id = neues Limit).
GLOBAL_LOGIN_MAX_FAILURES = 50
GLOBAL_LOGIN_KEY = "_global_"

# Markdown-Mini: nur fett, kursiv, Code, Links (sicher escaped)
import re as _re
_MD_BOLD = _re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = _re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_MD_CODE = _re.compile(r"`([^`]+)`")
_MD_LINK = _re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")

# Standard-Kategorien (werden beim ersten Start angelegt)
DEFAULT_CATEGORIES = [
    {"id": "allgemein", "name": "Allgemein", "desc": "Allgemeine Diskussionen"},
    {"id": "technik", "name": "Technik", "desc": "Erebos, Krypto, Netzwerk"},
    {"id": "support", "name": "Support", "desc": "Hilfe und Fragen"},
    {"id": "offtopic", "name": "Off-Topic", "desc": "Alles andere"},
]
THREADS_PER_PAGE = 20


def _hash_password(password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
    """PBKDF2-HMAC-SHA256. Liefert (hash, salt)."""
    if salt is None:
        salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return h, salt


def _verify_password(password: str, expected_hash: bytes, salt: bytes) -> bool:
    h, _ = _hash_password(password, salt)
    return secrets.compare_digest(h, expected_hash)


def _ensure_accounts(data: dict) -> dict:
    if "users" not in data:
        data["users"] = {}
    if "sessions" not in data:
        data["sessions"] = {}
    return data


def register_user(username: str, password: str) -> Tuple[bool, str]:
    """Legt einen Account an. Liefert (ok, message)."""
    username = _clean(username, MAX_USERNAME_LEN)
    if not username or len(username) < 2:
        return False, "Username zu kurz (min. 2 Zeichen)."
    if not _re.match(r"^[A-Za-z0-9_.-]+$", username):
        return False, "Username: nur Buchstaben, Ziffern, _.- erlaubt."
    if len(password) < MIN_PASSWORD_LEN:
        return False, f"Passwort zu kurz (min. {MIN_PASSWORD_LEN} Zeichen)."
    data = _ensure_accounts(load_forum())
    for existing in data["users"].values():
        if existing.get("username", "").lower() == username.lower():
            return False, "Username bereits vergeben."
    pwd_hash, salt = _hash_password(password)
    data["users"][username] = {
        "username": username,
        "password_hash": pwd_hash.hex(),
        "salt": salt.hex(),
        "created_at": time.time(),
    }
    save_forum(data)
    return True, "Account erstellt. Bitte einloggen."


def _check_login_rate(client_id: str) -> bool:
    """True = erlaubt, False = zu viele Fehlversuche.

    Prueft sowohl das per-Client-Limit (LOGIN_MAX_FAILURES) als auch
    das globale Sicherheitsnetz (GLOBAL_LOGIN_MAX_FAILURES). Letzteres
    verhindert Umgehung durch Cookie-Loeschen (neue client_id).
    """
    data = _ensure_accounts(load_forum())
    failures = data.setdefault("login_failures", {})
    now = time.time()

    # Per-Client: alte Eintraege entfernen
    per_client = [t for t in failures.get(client_id, []) if now - t < LOGIN_WINDOW_SECONDS]
    failures[client_id] = per_client

    # Global: alte Eintraege entfernen
    global_attempts = [
        t for t in failures.get(GLOBAL_LOGIN_KEY, [])
        if now - t < LOGIN_WINDOW_SECONDS
    ]
    failures[GLOBAL_LOGIN_KEY] = global_attempts

    save_forum(data)

    if len(per_client) >= LOGIN_MAX_FAILURES:
        return False
    if len(global_attempts) >= GLOBAL_LOGIN_MAX_FAILURES:
        logger.warning(
            f"Login-Rate-Limit GLOBAL erreicht "
            f"({len(global_attempts)}/{GLOBAL_LOGIN_MAX_FAILURES} in "
            f"{LOGIN_WINDOW_SECONDS}s)"
        )
        return False
    return True


def _record_login_failure(client_id: str) -> None:
    data = _ensure_accounts(load_forum())
    failures = data.setdefault("login_failures", {})
    now = time.time()
    failures.setdefault(client_id, []).append(now)
    failures.setdefault(GLOBAL_LOGIN_KEY, []).append(now)
    count = len(failures[client_id])
    global_count = len(failures[GLOBAL_LOGIN_KEY])
    save_forum(data)
    # Sicherheits-Warnung (OWASP A09:2025 Logging & Alerting)
    if count >= LOGIN_MAX_FAILURES:
        logger.warning(
            f"SECURITY: Login-Rate-Limit erreicht "
            f"(client={client_id[:16]}..., {count} Fehlversuche)"
        )
    elif count == 1:
        logger.info(f"Login-Fehlversuch (client={client_id[:16]}...)")
    if global_count >= GLOBAL_LOGIN_MAX_FAILURES:
        logger.warning(
            f"SECURITY: GLOBALES Login-Rate-Limit erreicht "
            f"({global_count} Fehlversuche in {LOGIN_WINDOW_SECONDS}s)"
        )


def _clear_login_failures(client_id: str) -> None:
    """Loescht die per-Client-Fehlversuche nach erfolgreichem Login.

    Die globalen Fehlversuche bleiben erhalten (sonst koennte ein
    erfolgreicher Login das globale Sicherheitsnetz zuruecksetzen).
    """
    data = _ensure_accounts(load_forum())
    failures = data.setdefault("login_failures", {})
    if client_id in failures:
        del failures[client_id]
        save_forum(data)


def login_user(username: str, password: str,
               client_id: str = "") -> tuple:
    """Prueft Login. Liefert (session_token, reason).

    reason: None (Erfolg), "invalid" (falsches Passwort),
            "rate_limit" (zu viele Fehlversuche).
    """
    if client_id and not _check_login_rate(client_id):
        logger.warning(f"Login-Rate-Limit erreicht (client={client_id[:8]})")
        return (None, "rate_limit")
    username = _clean(username, MAX_USERNAME_LEN)
    data = _ensure_accounts(load_forum())
    user = data["users"].get(username)
    if user is None:
        # Case-insensitive Fallback
        for u in data["users"].values():
            if u.get("username", "").lower() == username.lower():
                user = u
                break
    if user is None:
        if client_id:
            _record_login_failure(client_id)
        return (None, "invalid")
    try:
        expected = bytes.fromhex(user["password_hash"])
        salt = bytes.fromhex(user["salt"])
    except (KeyError, ValueError):
        if client_id:
            _record_login_failure(client_id)
        return (None, "invalid")
    if not _verify_password(password, expected, salt):
        if client_id:
            _record_login_failure(client_id)
        return (None, "invalid")
    # Erfolg: Fehlversuche loeschen
    if client_id:
        _clear_login_failures(client_id)
    # Session-Fixation-Schutz: alle alten Sessions des Users loeschen
    old_tokens = [
        tok for tok, sess in data["sessions"].items()
        if sess.get("username", "").lower() == user["username"].lower()
    ]
    for tok in old_tokens:
        del data["sessions"][tok]

    token = secrets.token_urlsafe(32)
    data["sessions"][token] = {
        "username": user["username"],
        "created_at": time.time(),
        "expires_at": time.time() + SESSION_TTL_SECONDS,
    }
    save_forum(data)
    return (token, None)


def logout_user(token: str) -> bool:
    data = _ensure_accounts(load_forum())
    if token in data["sessions"]:
        del data["sessions"][token]
        save_forum(data)
        return True
    return False


def get_session_user(session_cookie_value: str) -> Optional[str]:
    """Liefert den Username zur Session oder None (abgelaufen/ungueltig)."""
    if not session_cookie_value:
        return None
    data = _ensure_accounts(load_forum())
    sess = data["sessions"].get(session_cookie_value)
    if sess is None:
        return None
    if sess.get("expires_at", 0) < time.time():
        del data["sessions"][session_cookie_value]
        save_forum(data)
        return None
    return sess.get("username")


def _cleanup_sessions(data: dict) -> None:
    now = time.time()
    data["sessions"] = {
        tok: s for tok, s in data.get("sessions", {}).items()
        if s.get("expires_at", 0) >= now
    }


def get_or_create_client_id(cookie_header: str) -> Tuple[str, bool]:
    """Liest forum_client_id aus dem Cookie-Header oder erzeugt eine neue ID.

    Returns:
        (client_id, is_new)
    """
    if cookie_header:
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(CLIENT_COOKIE + "="):
                value = part[len(CLIENT_COOKIE) + 1 :].strip()
                if value and len(value) <= 64:
                    return value, False
    return uuid.uuid4().hex, True


def admin_token() -> str:
    """Admin-Token aus Env (Default 'changeme')."""
    return os.environ.get("EREBOS_FORUM_ADMIN_TOKEN", "changeme")


def admin_login(token: str) -> Optional[str]:
    """Prueft das Token. Liefert Cookie-Wert (oder None).

    Der Cookie-Wert ist ein frisch generiertes Secret, nicht das
    Token selbst — damit steht das Token nicht im Cookie.
    """
    if not token or token != admin_token():
        return None
    return secrets.token_urlsafe(32)


def is_admin(token: Optional[str]) -> bool:
    return bool(token) and token == admin_token()


def is_admin_cookie(cookie_value: str, client_id: str = "") -> bool:
    """Prueft, ob ein Cookie-Wert ein gueltiges Admin-Cookie ist.

    Der Cookie-Wert ist ein Secret, das bei admin_login() generiert
    wurde. Wir speichern ihn in forum.json["admin_sessions"].

    Wenn client_id angegeben ist, muss die Session an genau diese
    client_id gebunden sein (Schutz gegen Cookie-Diebstahl). Wenn
    client_id leer ist, wird die Bindung nicht geprueft
    (Backward-Compat).
    """
    if not cookie_value:
        return False
    data = load_forum()
    sessions = data.get("admin_sessions", {})
    sess = sessions.get(cookie_value)
    if sess is None:
        return False
    if sess.get("expires_at", 0) < time.time():
        del sessions[cookie_value]
        save_forum(data)
        return False
    # Client-Bindung pruefen
    bound_client = sess.get("client_id", "")
    if bound_client and client_id and bound_client != client_id:
        logger.warning(
            f"Admin-Cookie fuer fremden Client verworfen "
            f"(bound={bound_client[:8]}..., current={client_id[:8]}...)"
        )
        return False
    return True


def _store_admin_session(cookie_value: str, client_id: str = "") -> None:
    data = load_forum()
    if "admin_sessions" not in data:
        data["admin_sessions"] = {}
    data["admin_sessions"][cookie_value] = {
        "created_at": time.time(),
        "expires_at": time.time() + ADMIN_COOKIE_TTL_SECONDS,
        "client_id": client_id,
    }
    save_forum(data)


def _cleanup_admin_sessions(data: dict) -> None:
    now = time.time()
    data["admin_sessions"] = {
        tok: s for tok, s in data.get("admin_sessions", {}).items()
        if s.get("expires_at", 0) >= now
    }


_MIGRATED = False


def _ensure_structure(data: dict) -> dict:
    global _MIGRATED
    if not _MIGRATED:
        try:
            _migrate_from_json(FORUM_JSON_PATH)
        except Exception as e:
            logger.warning(f"Migration fehlgeschlagen: {e}")
        _MIGRATED = True
    """Stellt sicher, dass admin_token, rate_log, categories vorhanden sind."""
    if "admin_token" not in data:
        data["admin_token"] = admin_token()
    if not data.get("categories"):
        # Keine Kategorien in DB -> Defaults anlegen
        data["categories"] = list(DEFAULT_CATEGORIES)
        try:
            save_forum(data)
        except Exception as e:
            logger.warning(f"Kategorien konnten nicht gespeichert werden: {e}")
    else:
        # Sicherstellen, dass jede Kategorie id und name hat
        data["categories"] = [
            c for c in data["categories"]
            if isinstance(c, dict) and c.get("id") and c.get("name")
        ]
    # Migration: Threads ohne category_id -> "allgemein"
    for t in data.get("threads", []):
        if "category_id" not in t:
            t["category_id"] = "allgemein"
        # Sticky/Locked default False
        t.setdefault("sticky", False)
        t.setdefault("locked", False)
    # Accounts/Sessions/Reports/Bans/Mod-Log
    _ensure_accounts(data)
    data.setdefault("reports", [])
    data.setdefault("bans", [])
    data.setdefault("mod_log", [])
    data.setdefault("login_failures", {})
    if "rate_log" not in data:
        data["rate_log"] = {
            "threads": {},
            "replies": {},
            "global_threads": [],
            "global_replies": [],
        }
    else:
        # Migration: altes Format {"threads": [ts,...]} -> {"threads": {client: [ts]}}
        rl = data["rate_log"]
        if isinstance(rl.get("threads"), list):
            rl["threads"] = {}
        if isinstance(rl.get("replies"), list):
            rl["replies"] = {}
        rl.setdefault("threads", {})
        rl.setdefault("replies", {})
        rl.setdefault("global_threads", [])
        rl.setdefault("global_replies", [])
    return data


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def load_forum() -> dict:
    """Laedt die Forum-Daten aus SQLite (oder initialisiert leer)."""
    try:
        data = _load_from_db()
        if isinstance(data, dict) and "threads" in data:
            return _ensure_structure(data)
    except Exception as e:
        logger.warning(f"Forum-DB konnte nicht geladen werden: {e}")
    return _ensure_structure({"threads": []})


def save_forum(data: dict) -> bool:
    """Schreibt die Forum-Daten nach SQLite (Transaktion)."""
    try:
        return _save_to_db(data)
    except Exception as e:
        logger.error(f"Forum-DB konnte nicht geschrieben werden: {e}")
        return False


def parse_form_body(body_bytes: bytes) -> dict:
    """Parst application/x-www-form-urlencoded."""
    if not body_bytes:
        return {}
    try:
        text = body_bytes.decode("utf-8", "replace")
        parsed = parse_qs(text, keep_blank_values=True)
        return {k: v[0] if v else "" for k, v in parsed.items()}
    except Exception:
        return {}


def _clean(value: str, max_len: int) -> str:
    return (value or "").strip()[:max_len]


def create_thread(title: str, author: str, body: str,
                  client_id: str = "", category_id: str = "allgemein") -> Optional[str]:
    """Legt einen neuen Thread an. Gibt die Thread-ID zurueck (oder None)."""
    title = _clean(title, MAX_TITLE)
    body = _clean(body, MAX_BODY)
    author = _clean(author, MAX_AUTHOR) or "Anonym"
    category_id = _clean(category_id, 64) or "allgemein"
    if not title or not body:
        return None
    if is_banned(author):
        logger.warning(f"Thread von gebanntem User {author} blockiert")
        return None
    data = load_forum()
    if not _check_rate(data, client_id, "threads"):
        logger.warning(f"Rate-Limit erreicht (client={client_id[:8]}): zu viele Threads")
        return None
    thread_id = secrets.token_hex(6)
    now = time.time()
    data["threads"].insert(0, {
        "id": thread_id,
        "category_id": category_id,
        "title": title,
        "author": author,
        "created_at": now,
        "last_activity": now,
        "posts": [{
            "author": author,
            "body": body,
            "created_at": now,
        }],
    })
    _record_action(data, client_id, "threads")
    _cleanup_rate_log(data)
    if save_forum(data):
        return thread_id
    return None


def add_reply(thread_id: str, author: str, body: str,
              client_id: str = "") -> bool:
    """Fuegt einem Thread eine Antwort hinzu."""
    body = _clean(body, MAX_BODY)
    author = _clean(author, MAX_AUTHOR) or "Anonym"
    if not body:
        return False
    data = load_forum()
    if not _check_rate(data, client_id, "replies"):
        logger.warning(f"Rate-Limit erreicht (client={client_id[:8]}): zu viele Antworten")
        return False
    if is_banned(author):
        logger.warning(f"Antwort von gebanntem User {author} blockiert")
        return False
    for t in data["threads"]:
        if t["id"] == thread_id:
            if t.get("locked", False):
                logger.warning(f"Thread {thread_id} ist gesperrt")
                return False
            t["posts"].append({
                "author": author,
                "body": body,
                "created_at": time.time(),
            })
            t["last_activity"] = time.time()
            _record_action(data, client_id, "replies")
            _cleanup_rate_log(data)
            return save_forum(data)
    return False


def _check_rate(data: dict, client_id: str, kind: str) -> bool:
    """Prueft das Rate-Limit (pro Client + global). True = erlaubt."""
    now = time.time()
    rl = data["rate_log"]
    # Per-Client: alte Eintraege entfernen
    per_client = rl[kind].get(client_id, [])
    per_client = [t for t in per_client if now - t < RATE_WINDOW_SECONDS]
    rl[kind][client_id] = per_client
    max_client = RATE_MAX_THREADS if kind == "threads" else RATE_MAX_REPLIES
    if len(per_client) >= max_client:
        return False
    # Global: alte Eintraege entfernen
    global_key = "global_" + kind
    rl[global_key] = [t for t in rl[global_key] if now - t < RATE_WINDOW_SECONDS]
    max_global = GLOBAL_MAX_THREADS if kind == "threads" else GLOBAL_MAX_REPLIES
    if len(rl[global_key]) >= max_global:
        return False
    return True


def _record_action(data: dict, client_id: str, kind: str) -> None:
    now = time.time()
    rl = data["rate_log"]
    rl[kind].setdefault(client_id, []).append(now)
    rl["global_" + kind].append(now)


def _cleanup_rate_log(data: dict) -> None:
    """Entfernt leere Per-Client-Listen und alte globale Eintraege."""
    now = time.time()
    rl = data["rate_log"]
    for kind in ("threads", "replies"):
        rl[kind] = {
            cid: [t for t in ts if now - t < RATE_WINDOW_SECONDS]
            for cid, ts in rl[kind].items()
        }
        rl[kind] = {cid: ts for cid, ts in rl[kind].items() if ts}
        rl["global_" + kind] = [
            t for t in rl["global_" + kind] if now - t < RATE_WINDOW_SECONDS
        ]


def rate_limit_status(client_id: str = "") -> dict:
    """Liefert den aktuellen Stand (fuer Doku/Tests)."""
    data = load_forum()
    now = time.time()
    rl = data["rate_log"]
    threads = [t for t in rl["threads"].get(client_id, []) if now - t < RATE_WINDOW_SECONDS]
    replies = [t for t in rl["replies"].get(client_id, []) if now - t < RATE_WINDOW_SECONDS]
    return {
        "client_id": client_id or "(kein Cookie)",
        "threads_used": len(threads),
        "threads_max": RATE_MAX_THREADS,
        "replies_used": len(replies),
        "replies_max": RATE_MAX_REPLIES,
        "global_threads_used": len(
            [t for t in rl["global_threads"] if now - t < RATE_WINDOW_SECONDS]
        ),
        "global_replies_used": len(
            [t for t in rl["global_replies"] if now - t < RATE_WINDOW_SECONDS]
        ),
        "global_threads_max": GLOBAL_MAX_THREADS,
        "global_replies_max": GLOBAL_MAX_REPLIES,
        "window_seconds": RATE_WINDOW_SECONDS,
    }


def delete_thread(thread_id: str) -> bool:
    """Loescht einen Thread."""
    data = load_forum()
    before = len(data["threads"])
    data["threads"] = [t for t in data["threads"] if t["id"] != thread_id]
    if len(data["threads"]) == before:
        return False
    return save_forum(data)


def delete_post(thread_id: str, index: int) -> bool:
    """Loescht einen Post (index 0 = Eroeffnungsbeitrag -> Thread loeschen)."""
    data = load_forum()
    for t in data["threads"]:
        if t["id"] == thread_id:
            posts = t.get("posts", [])
            if index < 0 or index >= len(posts):
                return False
            if index == 0:
                # Eroeffnungsbeitrag: ganzen Thread loeschen
                data["threads"] = [x for x in data["threads"] if x["id"] != thread_id]
            else:
                del posts[index]
            return save_forum(data)
    return False


def edit_post(thread_id: str, index: int, new_body: str) -> bool:
    """Editiert den Body eines Posts (nicht den Autor)."""
    new_body = _clean(new_body, MAX_BODY)
    if not new_body:
        return False
    data = load_forum()
    for t in data["threads"]:
        if t["id"] == thread_id:
            posts = t.get("posts", [])
            if index < 0 or index >= len(posts):
                return False
            posts[index]["body"] = new_body
            posts[index]["edited_at"] = time.time()
            return save_forum(data)
    return False


def delete_posts_by_author(author: str) -> dict:
    """Loescht alle Posts eines Autors thread-uebergreifend."""
    author = _clean(author, MAX_AUTHOR)
    if not author:
        return {"threads_deleted": 0, "posts_deleted": 0}
    data = load_forum()
    threads_deleted = 0
    posts_deleted = 0
    new_threads = []
    for t in data["threads"]:
        posts = t.get("posts", [])
        if not posts:
            new_threads.append(t)
            continue
        if posts[0].get("author") == author:
            threads_deleted += 1
            posts_deleted += len(posts)
            continue
        kept = [posts[0]] + [p for p in posts[1:] if p.get("author") != author]
        removed = len(posts) - len(kept)
        if removed > 0:
            posts_deleted += removed
            t["posts"] = kept
        new_threads.append(t)
    data["threads"] = new_threads
    save_forum(data)
    return {"threads_deleted": threads_deleted, "posts_deleted": posts_deleted}


def list_authors() -> list:
    """Liefert eine sortierte Liste aller Autoren mit Post-Zaehler."""
    data = load_forum()
    counts = {}
    for t in data["threads"]:
        for p in t.get("posts", []):
            a = p.get("author", "?")
            counts[a] = counts.get(a, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def list_categories() -> list:
    """Liefert Kategorien mit Thread- und Post-Zaehler + letztem Thread."""
    data = load_forum()
    result = []
    for c in data.get("categories", []):
        cid = c["id"]
        threads = [t for t in data["threads"] if t.get("category_id") == cid]
        posts_count = sum(len(t.get("posts", [])) for t in threads)

        # Letzter Thread: Thread mit dem neuesten Post
        last_thread = None
        last_post = None
        best_ts = None
        for t in threads:
            for p in t.get("posts", []):
                ts = p.get("created_at")
                if ts is not None and (best_ts is None or ts > best_ts):
                    best_ts = ts
                    last_thread = t
                    last_post = p
        if last_thread is None and threads:
            # Fallback: erster Thread (falls keine Posts)
            last_thread = threads[0]

        # last_thread als dict mit title, time, author, id
        lt_dict = None
        if last_thread:
            import datetime as _dt
            ts = best_ts
            if ts is not None:
                try:
                    lt_time = _dt.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
                except Exception:
                    lt_time = ""
            else:
                lt_time = ""
            author = ""
            if last_post:
                author = last_post.get("author", "") or ""
            if not author and last_thread:
                author = last_thread.get("author", "") or ""
            if not author:
                author = "Anonym"
            lt_dict = {
                "id": last_thread.get("id", ""),
                "title": last_thread.get("title", ""),
                "time": lt_time,
                "author": author,
            }

        result.append({
            "id": cid,
            "name": c["name"],
            "desc": c.get("desc", ""),
            "threads_count": len(threads),
            "posts_count": posts_count,
            "last_thread": lt_dict,
        })
    return result


def get_category(category_id: str) -> Optional[dict]:
    data = load_forum()
    for c in data.get("categories", []):
        if c["id"] == category_id:
            return c
    return None


def list_threads_paged(category_id: Optional[str] = None,
                       sort: str = "active",
                       page: int = 1,
                       per_page: int = THREADS_PER_PAGE) -> dict:
    """Liefert paginierte Threads (optional nach Kategorie gefiltert).

    sort: "new" (created_at), "active" (last_activity), "replies" (posts)
    """
    data = load_forum()
    threads = data.get("threads", [])
    if category_id:
        threads = [t for t in threads if t.get("category_id") == category_id]

    if sort == "new":
        threads = sorted(threads, key=lambda t: t.get("created_at", 0), reverse=True)
    elif sort == "replies":
        threads = sorted(threads, key=lambda t: len(t.get("posts", [])), reverse=True)
    else:  # active
        threads = sorted(
            threads,
            key=lambda t: t.get("last_activity", t.get("created_at", 0)),
            reverse=True,
        )

    total = len(threads)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    page_threads = threads[start:start + per_page]

    return {
        "threads": page_threads,
        "total": total,
        "page": page,
        "pages": pages,
        "per_page": per_page,
        "sort": sort,
        "category_id": category_id,
    }


def search_threads(query: str, limit: int = 50) -> list:
    """Volltextsuche in Titel + Post-Bodies (case-insensitive)."""
    q = (query or "").strip().lower()
    if not q:
        return []
    data = load_forum()
    results = []
    for t in data["threads"]:
        title_match = q in t.get("title", "").lower()
        posts = t.get("posts", [])
        for idx, p in enumerate(posts):
            body = p.get("body", "").lower()
            if title_match or q in body:
                results.append({
                    "thread": t,
                    "matched_post_index": idx if q in body else -1,
                })
                break
    return results[:limit]


def _avatar_html(username: str, size: int = 32) -> str:
    """Initialen-Avatar mit deterministischer Farbe aus dem Username."""
    import hashlib
    safe = username or "Anonym"
    h = int(hashlib.md5(safe.encode()).hexdigest()[:8], 16)
    hue = h % 360
    initials = (safe[:2] if len(safe) >= 2 else safe[:1]).upper()
    return (
        f'<span class="forum-avatar" style="'
        f'width:{size}px;height:{size}px;'
        f'background:hsl({hue},55%,45%);'
        f'font-size:{max(10, size//2.5)}px;'
        f'">{_escape(initials)}</span>'
    )

def get_forum_css() -> str:
    """Zentrales CSS für das Forum (Avatare, Cards, Layout)."""
    return """<style>
/* --- Globale Einstellungen für ruhiges Hovern --- */
* {
    box-sizing: border-box;
}
button, .btn, .category-card, .thread-card, .post-card, input, textarea, a {
    -webkit-tap-highlight-color: transparent;
    outline: none;
}

/* --- Grundlagen --- */
.forum-main { max-width: 900px; margin: 0 auto; padding: 1rem; }
.btn { 
    display: inline-block; 
    padding: 8px 16px; 
    background: #21262d; 
    color: #c9d1d9; 
    border-radius: 6px; 
    text-decoration: none; 
    font-weight: 600; 
    transition: background-color .3s ease, border-color .3s ease, color .3s ease; 
    border: 1px solid #30363d; 
    cursor: pointer; 
    font-size: 0.9em; 
    line-height: 1.4;
    /* Verhindert, dass der Button beim Klick "eindrückt" */
    transform: none !important;
}
.btn:hover { background: #da3633; border-color: #ff3333; color: #fff; }
.btn:active { transform: none !important; background: #ff3333; }
.muted { color: #7d8590; }

/* --- Avatare --- */
.forum-avatar-img { 
    display: inline-block; 
    vertical-align: middle; 
    border-radius: 50%; 
    object-fit: cover; 
    border: 2px solid #ff3333; 
    flex-shrink: 0;
    /* Feste Größe, kein Mitschrumpfen */
    width: var(--avatar-size, 64px);
    height: var(--avatar-size, 64px);
}
.forum-avatar { 
    display: inline-flex; 
    align-items: center; 
    justify-content: center; 
    border-radius: 50%; 
    color: #fff; 
    font-weight: 700; 
    vertical-align: middle; 
    margin-right: 12px; 
    flex-shrink: 0; 
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
    text-shadow: 0 1px 2px rgba(0,0,0,.5); 
    width: var(--avatar-size, 64px);
    height: var(--avatar-size, 64px);
}

/* --- Gemeinsame Card-Basis (Kategorie, Thread, Post) --- */
.category-card, .thread-card, .post-card {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    padding: 1.5em 2em; 
    margin: 1em 0;      
    border: 1px solid #30363d;
    border-radius: 8px;
    background: #0d1117;
    color: inherit;
    text-decoration: none;
    transition: border-color .3s ease, background-color .3s ease;
    width: 100%;
    box-sizing: border-box;
    transform: none !important;
}

/* Die linke Seite der Karte (Name, Beschreibung, letzter Thread) */
.category-info, .thread-info {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
}

/* Die rechte Seite der Karte (Threads / Posts) */
.category-stats {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    text-align: right;
    color: #8b949e;
    font-size: .85em;
    line-height: 1.6;
    background: transparent;
    padding: 0;
    border: none;
}
/* Hover: nur Farbe, kein Springen */
.category-card:hover, .thread-card:hover, .post-card:hover {
    border-color: #ff3333;
    background-color: #1a1010;
    transform: none !important;
}
.category-card:active, .thread-card:active, .post-card:active {
    transform: none !important;
}

/* --- Inhalte innerhalb der Cards --- */
.category-info, .thread-info, .post-body { 
    flex: 1; 
    min-width: 0; 
}
.category-info strong, .thread-info strong { 
    display: block; 
    font-size: 1.1em; 
    margin-bottom: 4px; 
    color: #e6edf3; 
    line-height: 1.3;
}
.category-desc, .thread-meta { 
    color: #7d8590; 
    font-size: .88em; 
    margin: 4px 0 0 0; 
    line-height: 1.4;
}
.category-stats { 
    color: #8b949e; 
    font-size: .85em; 
    white-space: nowrap; 
    text-align: right; 
    flex-shrink: 0;
    align-self: center;
    margin-left: 20px;
}

/* --- Post-spezifisch --- */
.post-head { 
    display: flex; 
    align-items: center; 
    gap: 8px; 
    margin-bottom: 12px; 
    flex-wrap: wrap; 
    border-bottom: 1px solid #21262d; 
    padding-bottom: 12px; 
    min-height: 40px;
}
.post-head strong { font-size: 1.05em; color: #e6edf3; }
.post-head time, .post-head small { color: #7d8590; font-size: .85em; }
.post-body p { margin: .6em 0; line-height: 1.6; word-wrap: break-word; }

/* --- Profil --- */
.profile-container { 
    background: #0d1117; 
    border: 1px solid #30363d; 
    border-radius: 8px; 
    padding: 2em; 
    margin: 1em 0; 
}
.profile-header { 
    display: flex; 
    align-items: center; 
    gap: 20px; 
    margin-bottom: 2em; 
    border-bottom: 1px solid #21262d; 
    padding-bottom: 1.5em; 
}
.profile-avatar-large { 
    width: 100px; 
    height: 100px; 
    border-radius: 50%; 
    object-fit: cover; 
    border: 2px solid #ff3333; 
    flex-shrink: 0;
}
.form-group { margin-bottom: 1.5em; }
.form-group label { 
    display: block; 
    font-weight: 600; 
    margin-bottom: .5em; 
    color: #e6edf3; 
}
.form-group input[type="text"], .form-group textarea {
    width: 100%; 
    padding: 10px; 
    background: #161b22; 
    border: 1px solid #30363d;
    border-radius: 6px; 
    color: #c9d1d9; 
    font-family: inherit; 
    font-size: 1em;
    transition: border-color .3s ease;
    resize: vertical; /* Verhindert, dass Textareas beim Fokus springen */
}
.form-group input[type="text"]:focus, .form-group textarea:focus { 
    border-color: #ff3333; 
    outline: none; 
}
.file-input-btn { 
    display: inline-block; 
    padding: 8px 16px; 
    background: #21262d; 
    color: #c9d1d9; 
    border: 1px solid #30363d; 
    border-radius: 6px; 
    cursor: pointer; 
    font-size: 0.9em; 
    transition: background-color .3s ease, border-color .3s ease; 
}
.file-input-btn:hover { background: #30363d; border-color: #ff3333; color: #fff; }
.privacy-warning { 
    background: rgba(255, 51, 51, 0.08); 
    border-left: 4px solid #ff3333; 
    padding: 16px; 
    border-radius: 4px; 
    margin: 1.5em 0; 
    font-size: 0.9em; 
    color: #ffcccc; 
    line-height: 1.5;
}
.checkbox-group { 
    display: flex; 
    align-items: flex-start; 
    gap: 10px; 
    margin: 1.5em 0; 
    cursor: pointer; 
}
.checkbox-group input[type="checkbox"] { 
    margin-top: 4px; 
    width: 18px; 
    height: 18px; 
    accent-color: #da3633; 
    flex-shrink: 0;
}

/* Links */
a { color: #ff3333; text-decoration: none; transition: color .3s ease; }
a:hover { color: #ff6666; text-decoration: underline; }

/* Hintergrund */
body {
    background-color: #050508;
    background-image: 
        linear-gradient(rgba(5, 5, 8, 0.85), rgba(5, 5, 8, 0.95)),
        url('/static/hacker.jpeg');
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    background-repeat: no-repeat;
}

/* --- Auth-Seiten (Login / Registrieren) --- */
.auth-page-wrapper {
    position: relative;
    min-height: 70vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    background-image: 
        linear-gradient(rgba(5, 5, 8, 0.85), rgba(5, 5, 8, 0.95)),
        url('/static/auth.png');
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    background-repeat: no-repeat;
    border-radius: 8px;
    margin: 1rem 0;
}
.auth-container {
    max-width: 500px;
    width: 100%;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 2em;
    box-shadow: 0 4px 12px rgba(0,0,0,0.5);
}
.auth-form .form-group { margin-bottom: 1.2em; }
.auth-form label { display: block; margin-bottom: 0.5em; color: #e6edf3; font-weight: 600; }
.auth-form input {
    width: 100%; padding: 10px; background: #161b22; border: 1px solid #30363d;
    border-radius: 6px; color: #e6edf3; font-family: inherit; font-size: 1em;
    transition: border-color 0.3s ease;
}
.auth-form input:focus { border-color: #ff3333; outline: none; }
.auth-form .muted { display: block; margin-top: 0.5em; font-size: 0.8em; }
.btn-primary { background: #da3633; color: #fff; border-color: #ff3333; }
.btn-primary:hover { background: #ff3333; }
.btn-secondary { background: transparent; color: #8b949e; border-color: transparent; }
.btn-secondary:hover { color: #ff3333; background: transparent; text-decoration: underline; }
.form-error {
    background: rgba(255, 51, 51, 0.1); border-left: 4px solid #ff3333;
    color: #ffcccc; padding: 12px; border-radius: 4px; margin-bottom: 1.5em; font-size: 0.9em;
}
.security-note {
    background: rgba(255, 51, 51, 0.05); border: 1px solid rgba(255, 51, 51, 0.2);
    color: #ffcccc; padding: 12px; border-radius: 6px; margin-bottom: 1.5em; font-size: 0.85em; line-height: 1.5;
}
.auth-footer { margin-top: 1.5em; text-align: center; font-size: 0.9em; }
.auth-footer a { color: #ff3333; text-decoration: none; }
.auth-footer a:hover { text-decoration: underline; }

/* --- Forum-Layout (Header, Sidebar, Main) --- */
.forum-header {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-bottom: 1.5em;
    padding: 1em 1.5em;
}
.header-inner {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 1em;
}
.logo {
    font-size: 1.3em;
    font-weight: 700;
    color: #ff3333;
    text-decoration: none;
    letter-spacing: 1px;
    text-shadow: 0 0 15px rgba(255, 51, 51, 0.3);
}
.top-nav {
    display: flex;
    gap: 1.5em;
}
.top-nav a {
    color: #8b949e;
    text-decoration: none;
    font-size: 0.95em;
    transition: color .3s ease;
}
.top-nav a:hover {
    color: #ff3333;
}

.forum-layout {
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: 2em;
}
@media (max-width: 768px) {
    .forum-layout { grid-template-columns: 1fr; }
}

.forum-sidebar {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1.5em;
    align-self: start;
}
.forum-sidebar h3 {
    color: #ff3333;
    font-size: 0.9em;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 1em;
    border-bottom: 1px solid #21262d;
    padding-bottom: 0.5em;
}
.sidebar-nav {
    list-style: none;
    padding: 0;
    margin: 0;
}
.sidebar-nav li {
    margin-bottom: 0.8em;
    color: #8b949e;
    font-size: 0.9em;
    line-height: 1.4;
}
.sidebar-nav a {
    color: #e6edf3;
    text-decoration: none;
    font-weight: 600;
    transition: color .3s ease;
}
.sidebar-nav a:hover {
    color: #ff3333;
}

.forum-main {
    min-width: 0;
}
.forum-main h1 {
    margin-bottom: 0.5em;
}

.category-list {
    display: flex;
    flex-direction: column;
    gap: 0.5em;
    margin: 1.5em 0;
}

.legend {
    background: #0d1117;
    border: 1px solid #30363d;
    border-left: 3px solid #ff3333;
    border-radius: 4px;
    padding: 0.8em 1em;
    margin: 1em 0;
    font-size: 0.85em;
    color: #8b949e;
}
.legend strong {
    color: #e6edf3;
}

/* --- Sidebar Feinschliff --- */
.sidebar-nav li {
    margin-bottom: 1.2em;
}
.sidebar-nav li small {
    display: block;
    margin-top: 0.2em;
    color: #8b949e;
    font-size: 0.75em;
    line-height: 1.4;
}

/* --- Legende (ersetzt das alte Inline-Styling) --- */
.legend {
    background: rgba(255, 51, 51, 0.05);
    border: 1px solid rgba(255, 51, 51, 0.2);
    border-left: 3px solid #ff3333;
    border-radius: 4px;
    padding: 1em;
    margin: 1.5em 0;
    font-size: 0.85em;
    color: #8b949e;
}
.legend strong { color: #e6edf3; }

/* --- Suchformular --- */
.forum-search {
    display: flex;
    gap: 0.5em;
    margin: 1.5em 0;
}
.forum-search input {
    flex: 1;
    padding: 0.8em 1em;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    font-family: inherit;
    font-size: 1em;
    transition: border-color 0.3s ease;
}
.forum-search input:focus {
    border-color: #ff3333;
    outline: none;
}
</style>"""

# ============================================================
# Profil-Funktionen
# ============================================================

def get_user_profile(username: str) -> dict:
    """Liefert das Profil eines Users (bio, avatar_path, profile_confirmed)."""
    from .forum_db import get_db
    if not username:
        return {}
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT username, bio, avatar_path, profile_confirmed, created_at "
            "FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return {}
        return {
            "username": row[0],
            "bio": row[1] or "",
            "avatar_path": row[2] or "",
            "profile_confirmed": bool(row[3]),
            "created_at": row[4],
        }
    except Exception as e:
        logger.warning(f"get_user_profile fehlgeschlagen: {e}")
        return {}


def update_user_profile(username: str, bio: str,
                        avatar_data_b64: str = "",
                        confirm_no_private_data: bool = False) -> tuple:
    """Aktualisiert das Profil. Gibt (ok, msg) zurück.

    avatar_data_b64: Base64-String eines Data-URL (data:image/...;base64,...)
    """
    if not username:
        return (False, "Nicht eingeloggt.")
    if not confirm_no_private_data:
        return (False, "Bitte bestätige den Datenschutz-Hinweis.")
    if len(bio) > 500:
        return (False, "Bio darf maximal 500 Zeichen lang sein.")
    from .forum_db import get_db
    avatar_path = ""
    if avatar_data_b64:
        ok, result = _save_avatar(username, avatar_data_b64)
        if not ok:
            return (False, result)
        avatar_path = result
    try:
        conn = get_db()
        if avatar_path:
            conn.execute(
                "UPDATE users SET bio = ?, avatar_path = ?, profile_confirmed = 1 "
                "WHERE username = ?",
                (bio.strip(), avatar_path, username),
            )
        else:
            conn.execute(
                "UPDATE users SET bio = ?, profile_confirmed = 1 "
                "WHERE username = ?",
                (bio.strip(), username),
            )
        conn.commit()
        return (True, "Profil gespeichert.")
    except Exception as e:
        logger.error(f"update_user_profile fehlgeschlagen: {e}")
        return (False, f"Fehler: {e}")


def _save_avatar(username: str, data_b64: str) -> tuple:
    """Speichert einen Base64-Data-URL als Avatar-Bild.

    Erlaubt: JPEG, PNG, GIF, WebP. Max. 200 KB.
    Speichert in src/erebos_network/static/avatars/<username>.<ext>.
    """
    import base64
    from pathlib import Path as _P
    if len(data_b64) > 300_000:  # ~200 KB nach Base64
        return (False, "Bild zu groß (max. ~200 KB).")
    if "," in data_b64:
        meta, b64 = data_b64.split(",", 1)
    else:
        return (False, "Ungültiges Bild-Format.")
    # MIME-Type aus meta lesen: data:image/jpeg;base64
    mime = "image/jpeg"
    if "image/" in meta:
        mime = meta.split(";")[0].replace("data:", "")
    ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
    }
    if mime not in ext_map:
        return (False, f"Bild-Typ nicht erlaubt ({mime}). Nur JPEG, PNG, GIF, WebP.")
    ext = ext_map[mime]
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return (False, "Base64-Decode fehlgeschlagen.")
    if len(raw) > 250_000:
        return (False, "Bild zu groß (max. 250 KB nach Decode).")
    # Magic-Bytes prüfen
    magic = raw[:8]
    if not (
        magic.startswith(b"\xff\xd8\xff")  # JPEG
        or magic.startswith(b"\x89PNG")      # PNG
        or magic.startswith(b"GIF8")           # GIF
        or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")  # WebP
    ):
        return (False, "Datei ist kein gültiges Bild.")
    # Speichern
    base_dir = _P(__file__).parent / "static" / "avatars"
    base_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{username}.{ext}"
    fpath = base_dir / fname
    try:
        fpath.write_bytes(raw)
    except Exception as e:
        return (False, f"Speichern fehlgeschlagen: {e}")
    return (True, f"/static/avatars/{fname}")


def _avatar_url(username: str) -> str:
    """Liefert die Avatar-URL oder '' wenn kein Avatar gesetzt."""
    prof = get_user_profile(username)
    return prof.get("avatar_path", "") or ""


def _avatar_html_or_initials(username: str, size: int = 32) -> str:
    """Avatar-Bild falls vorhanden, sonst hacker.jpeg als Standard."""
    url = _avatar_url(username)
    if not url:
        url = "/static/hacker.jpeg"  # Standard-Avatar
    return (
        f'<img class="forum-avatar-img" src="{_escape(url)}" '
        f'alt="{_escape(username)}" '
        f'style="width:{size}px;height:{size}px;border-radius:50%;'
        f'object-fit:cover;margin-right:12px;flex-shrink:0;'
        f'border:2px solid #ff3333;">'
    )


def render_markdown(text: str) -> str:
    """Sicheres Markdown-Mini ohne Regex (ReDoS-Schutz).

    Ersetzt **bold**, *italic*, `code`, [text](url) mit linearen
    String-Operationen. Max. 50 Ersetzungen pro Muster, damit die
    Laufzeit bei 4000-Zeichen-Posts begrenzt bleibt.
    """
    escaped = _escape(text).replace("\n", "<br>")
    MAX_REPLACEMENTS = 50

    # 1) Links: [text](url) — manueller Parser, linear
    out = []
    i = 0
    link_count = 0
    n = len(escaped)
    while i < n and link_count < MAX_REPLACEMENTS:
        if escaped[i] == "[":
            close = escaped.find("]", i + 1)
            if close != -1 and close + 1 < n and escaped[close + 1] == "(":
                end = escaped.find(")", close + 2)
                if end != -1:
                    label = escaped[i + 1:close]
                    url = escaped[close + 2:end]
                    # Steuerzeichen und Nicht-ASCII ablehnen
                    ok = url.startswith(("http://", "https://")) and url.isascii()
                    if ok and not any(ord(c) < 0x20 or 0x7f <= ord(c) <= 0x9f for c in url):
                        out.append(
                            f'<a href="{url}" rel="noopener noreferrer" '
                            f'target="_blank">{label}</a>'
                        )
                        link_count += 1
                        i = end + 1
                        continue
        out.append(escaped[i])
        i += 1
    escaped = "".join(out)

    # 2) **bold** — linear, max. 50
    for _ in range(MAX_REPLACEMENTS):
        start = escaped.find("**")
        if start == -1:
            break
        end = escaped.find("**", start + 2)
        if end == -1:
            break
        inner = escaped[start + 2:end]
        escaped = escaped[:start] + f"<strong>{inner}</strong>" + escaped[end + 2:]

    # 3) *italic* — linear, max. 50 (nur wenn nicht Teil von **)
    for _ in range(MAX_REPLACEMENTS):
        start = escaped.find("*")
        if start == -1:
            break
        end = escaped.find("*", start + 1)
        if end == -1:
            break
        inner = escaped[start + 1:end]
        if not inner or inner.startswith("*") or inner.endswith("*"):
            # Ueberspringe verschachtelte Sterne
            escaped = escaped[:start] + "\x00" + escaped[start + 1:]
            continue
        escaped = escaped[:start] + f"<em>{inner}</em>" + escaped[end + 1:]
    escaped = escaped.replace("\x00", "*")

    # 4) `code` — linear, max. 50
    for _ in range(MAX_REPLACEMENTS):
        start = escaped.find("`")
        if start == -1:
            break
        end = escaped.find("`", start + 1)
        if end == -1:
            break
        inner = escaped[start + 1:end]
        escaped = escaped[:start] + f"<code>{inner}</code>" + escaped[end + 1:]

    return escaped


def list_user_threads(username: str) -> list:
    data = load_forum()
    return [
        t for t in data["threads"]
        if any(p.get("author") == username for p in t.get("posts", []))
    ]


def report_post(thread_id: str, index: int, reason: str, reporter: str = "") -> bool:
    if reporter and reporter != "Anonym" and is_banned(reporter):
        logger.warning(f"Report von gebanntem User {reporter} blockiert")
        return False
    data = _ensure_accounts(load_forum())
    if "reports" not in data:
        data["reports"] = []
    for t in data["threads"]:
        if t["id"] == thread_id:
            if index < 0 or index >= len(t.get("posts", [])):
                return False
            data["reports"].append({
                "thread_id": thread_id,
                "post_index": index,
                "reason": _clean(reason, 500),
                "reporter": _clean(reporter, MAX_AUTHOR) or "Anonym",
                "created_at": time.time(),
                "resolved": False,
            })
            return save_forum(data)
    return False


def list_reports() -> list:
    data = _ensure_accounts(load_forum())
    return [r for r in data.get("reports", []) if not r.get("resolved")]


def resolve_report(index: int) -> bool:
    data = _ensure_accounts(load_forum())
    reports = data.get("reports", [])
    if index < 0 or index >= len(reports):
        return False
    reports[index]["resolved"] = True
    return save_forum(data)


def ban_user(username: str, reason: str = "") -> bool:
    data = _ensure_accounts(load_forum())
    if "bans" not in data:
        data["bans"] = []
    username = _clean(username, MAX_USERNAME_LEN)
    if not username:
        return False
    data["bans"].append({
        "username": username,
        "reason": _clean(reason, 500),
        "created_at": time.time(),
    })
    # Alle Sessions des Users invalidieren (Ban-Durchsetzung)
    sessions = data.get("sessions", {})
    to_remove = [
        token for token, sess in sessions.items()
        if sess.get("username", "").lower() == username.lower()
    ]
    for token in to_remove:
        del sessions[token]
    if to_remove:
        logger.info(f"Ban: {len(to_remove)} Session(s) von {username} invalidiert")
    logger.warning(f"SECURITY: User {username} gebannt (Grund: {reason or 'kein Grund'})")
    return save_forum(data)


def is_banned(username: str) -> bool:
    data = _ensure_accounts(load_forum())
    return any(
        b.get("username", "").lower() == username.lower()
        for b in data.get("bans", [])
    )


def toggle_sticky(thread_id: str) -> bool:
    data = load_forum()
    for t in data["threads"]:
        if t["id"] == thread_id:
            t["sticky"] = not t.get("sticky", False)
            return save_forum(data)
    return False


def toggle_locked(thread_id: str) -> bool:
    data = load_forum()
    for t in data["threads"]:
        if t["id"] == thread_id:
            t["locked"] = not t.get("locked", False)
            return save_forum(data)
    return False


def log_moderation(action: str, target: str, moderator: str = "admin") -> None:
    """Fuegt einen Eintrag in mod_log ein (ohne save_forum)."""
    try:
        insert_mod_log(action, target, moderator)
    except Exception:
        # Fallback: altes Verhalten (save_forum)
        data = _ensure_accounts(load_forum())
        if "mod_log" not in data:
            data["mod_log"] = []
        data["mod_log"].append({
            "action": action,
            "target": target,
            "moderator": moderator,
            "created_at": time.time(),
        })
        save_forum(data)


def list_mod_log(limit: int = 100) -> list:
    data = _ensure_accounts(load_forum())
    return list(reversed(data.get("mod_log", [])))[:limit]


def find_thread(thread_id: str) -> Optional[dict]:
    data = load_forum()
    for t in data["threads"]:
        if t["id"] == thread_id:
            return t
    return None


def _fmt_time(ts: float) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# HTML-Renderer
# ---------------------------------------------------------------------------

def render_forum_list(admin: bool = False, client_id: str = "") -> str:
    data = load_forum()
    threads = data.get("threads", [])
    if not threads:
        items = "<li><em>Noch keine Threads. <a href=\"/forum/neu\">Erstelle den ersten.</a></em></li>"
    else:
        items = ""
        for t in threads:
            tid = _escape(t["id"])
            title = _escape(t["title"])
            author = _escape(t["author"])
            replies = max(0, len(t.get("posts", [])) - 1)
            created = _fmt_time(t.get("created_at", 0))
            admin_btn = ""
            if mod:
                admin_btn = (
                    f" <form method=\"post\" action=\"/forum/{tid}/delete\" "
                    f"style=\"display:inline\"><button type=\"submit\" "
                    f"style=\"background:#c0392b;color:#fff;border:none;"
                    f"padding:0.2em 0.5em;border-radius:3px;cursor:pointer\">"
                    f"Löschen</button></form>"
                )
            items += (
                f"<li><a href=\"/forum/{tid}\">{title}</a> "
                f"<small>von {author} · {replies} Antwort(en) · {created}</small>"
                f"{admin_btn}</li>\n"
            )
    status = rate_limit_status(client_id)
    client_status = (
        f"<p><small>Dein Limit: {status['threads_used']} / {status['threads_max']} "
        f"Threads, {status['replies_used']} / {status['replies_max']} Antworten "
        f"(Fenster: {status['window_seconds'] // 60} Minuten)</small></p>\n"
    )
    return (
        ""
        "<p>Diskutiere mit anderen im Erebos-Netzwerk.</p>\n"
        f"{client_status}"
        f"<ul>\n{items}\n</ul>\n"
        "<a class=\"btn\" href=\"/forum/neu\">Neuen Thread erstellen</a>\n"
        "<a class=\"btn\" href=\"/\">← Startseite</a>\n"
    )





def render_thread(thread: dict, admin: bool = False, mod: bool = False) -> str:
    tid = _escape(thread["id"])
    title = _escape(thread["title"])
    posts_html = ""
    posts_list = thread.get("posts", [])
    last_idx = len(posts_list) - 1
    for idx, p in enumerate(posts_list):
        is_last = (idx == last_idx)
        last_anchor = ' id="last-post"' if is_last else ''
        author = _escape(p.get("author", "?"))
        body = render_markdown(p.get("body", ""))
        created = _fmt_time(p.get("created_at", 0))
        edited = p.get("edited_at")
        edited_marker = ""
        if edited:
            edited_marker = f" <small><em>(bearbeitet {_fmt_time(edited)})</em></small>"
        admin_btn = ""
        if mod:
            label = "Thread löschen" if idx == 0 else "Post löschen"
            admin_btn = (
                f" <form method=\"post\" action=\"/forum/{tid}/post/{idx}/delete\" "
                f"style=\"display:inline\"><button type=\"submit\" "
                f"style=\"background:#c0392b;color:#fff;border:none;"
                f"padding:0.2em 0.5em;border-radius:3px;cursor:pointer\">"
                f"{label}</button></form>"
                f" <a href=\"/forum/{tid}/post/{idx}/edit\" "
                f"style=\"background:#2980b9;color:#fff;text-decoration:none;"
                f"padding:0.2em 0.5em;border-radius:3px;font-size:0.85em\">"
                f"Bearbeiten</a>"
            )
        # Zitat-Button: fuehrt zu einer Quote-Route (kein Inline-JS,
        # weil CSP script-src 'none' blockiert)
        quote_btn = (
            f" <a href=\"/forum/{tid}/post/{idx}/quote\" "
            f"style=\"font-size:0.85em\">Zitieren</a>"
        )
        # Report-Button
        report_btn = (
            f" <a href=\"/forum/{tid}/post/{idx}/report\" "
            f"style=\"font-size:0.85em\">Melden</a>"
        )
        # Ban-Button (nur Admin, nur bei Posts mit benanntem Autor)
        ban_btn = ""
        if admin and p.get("author") and p.get("author") != "Anonym":
            ban_btn = (
                f" <form method=\"post\" action=\"/forum/admin/ban\" "
                f"style=\"display:inline\">"
                f"<input type=\"hidden\" name=\"username\" value=\"{_escape(p.get('author'))}\">"
                f"<button type=\"submit\" "
                f"style=\"background:#8e44ad;color:#fff;border:none;"
                f"padding:0.2em 0.5em;border-radius:3px;cursor:pointer;font-size:0.85em\">"
                f"User bannen</button></form>"
            )
        avatar = _avatar_html_or_initials(p.get("author", "Anonym"), size=40)
        posts_html += (
            f"<div{last_anchor} class=\"post-card\">\n"
            f"  {avatar}\n"
            f"  <div class=\"post-body\">\n"
            f"    <div class=\"post-head\">\n"
            f"      <strong>{author}</strong> <small>{created}</small>{edited_marker}\n"
            f"      <span style=\"margin-left:auto\">{quote_btn}{report_btn}{ban_btn}{admin_btn}</span>\n"
            f"    </div>\n"
            f"    <p>{body}</p>\n"
            f"  </div>\n"
            f"</div>\n"
        )
    sticky_locked = ""
    if thread.get("sticky"):
        sticky_locked += " <small>[sticky]</small>"
    if thread.get("locked"):
        sticky_locked += " <small>[gesperrt]</small>"
    if mod:
        tid_esc = _escape(thread["id"])
        sticky_locked += (
            f" <form method=\"post\" action=\"/forum/{tid_esc}/toggle/sticky\" "
            f"style=\"display:inline\"><button type=\"submit\" "
            f"style=\"font-size:0.75em;padding:0.2em 0.5em\">"
            f"{'Sticky aus' if thread.get('sticky') else 'Sticky an'}</button></form>"
            f" <form method=\"post\" action=\"/forum/{tid_esc}/toggle/locked\" "
            f"style=\"display:inline\"><button type=\"submit\" "
            f"style=\"font-size:0.75em;padding:0.2em 0.5em\">"
            f"{'Entsperren' if thread.get('locked') else 'Sperren'}</button></form>"
        )
    reply_block = ""
    if thread.get("locked"):
        reply_block = "<p><em>Dieser Thread ist gesperrt. Antworten nicht möglich.</em></p>\n"
    else:
        reply_block = (
            "<h2>Antworten</h2>\n"
            f"<form method=\"post\" action=\"/forum/{tid}/antwort\">\n"
            "  <p><label>Dein Name (optional):<br><input name=\"author\" maxlength=\"60\" placeholder=\"Anonym\" style=\"width:100%\"></label></p>\n"
            "  <p><label>Antwort:<br><textarea name=\"body\" rows=\"6\" maxlength=\"4000\" required style=\"width:100%\"></textarea></label></p>\n"
            "  <p><button type=\"submit\" class=\"btn\">Antwort senden</button></p>\n"
            "</form>\n"
        )
    # "Zum letzten Beitrag"-Anchor (nur wenn mehr als 1 Post)
    last_post_link = ""
    if len(posts_list) > 1:
        last_post_link = (
            '<p style="text-align:right; margin:0.5em 0;">'
            '<a href="#last-post" class="btn" style="font-size:0.85em;">'
            '↓ Zum letzten Beitrag</a></p>'
        )

    return (
        f"<p><a href=\"/forum\">← Zurück zum Forum</a></p>\n"
        f"<p class=\"thread-header-meta\">{sticky_locked}</p>\n"
        f"{last_post_link}"
        f"{posts_html}\n"
        f"{reply_block}"
    )




def render_profile_edit(username: str, profile: dict = None) -> str:
    """Profil-Bearbeiten-Formular (2026 Design)."""
    if profile is None:
        profile = get_user_profile(username) or {}
    bio = _escape(profile.get("bio", ""))
    avatar_url = profile.get("avatar_path", "")
    confirmed = profile.get("profile_confirmed", False)
    checked_attr = "checked" if confirmed else ""
    
    # Avatar-Vorschau
    if avatar_url:
        preview_img = f'<img id="avatar-preview" src="{_escape(avatar_url)}" class="profile-avatar-large" alt="Avatar">'
    else:
        # Initialen als Fallback
        fallback = _avatar_html(username, size=100).replace('class="forum-avatar"', 'class="profile-avatar-large"')
        preview_img = f'<div id="avatar-preview">{fallback}</div>'

    return f"""
    <div class="profile-container">
        <h2 style="margin-top:0; border-bottom:1px solid #30363d; padding-bottom:10px;">Profil bearbeiten</h2>
        <div class="profile-header">
            <div style="text-align:center;">
                {preview_img}
                <div style="margin-top:10px;">
                    <label for="avatar_file" class="file-input-btn">Bild auswählen</label>
                    <input type="file" id="avatar_file" name="avatar_file" accept="image/*" 
                        onchange="var f=this.files[0];if(!f)return;if(f.size>200000){{alert('Bild zu gross (max. 200 KB)');this.value='';return;}}var r=new FileReader();r.onload=function(){{document.getElementById('avatar_b64').value=r.result;document.getElementById('avatar-preview').innerHTML='<img src=\''+r.result+'\' class=\'profile-avatar-large\'>';}};r.readAsDataURL(f);">
                    <p class="muted" style="font-size:0.75em; margin-top:4px;">Max 200 KB (JPEG/PNG/GIF)</p>
                </div>
            </div>
            <div style="flex:1;">
                <h3 style="margin:0 0 5px 0;">{_escape(username)}</h3>
                <p class="muted" style="margin:0;">Dein Profil ist für alle im Erebos-Netzwerk sichtbar.</p>
            </div>
        </div>

        <form method="post" action="/forum/profil/edit" enctype="application/x-www-form-urlencoded">
            <input type="hidden" id="avatar_b64" name="avatar_b64" value="">
            
            <div class="form-group">
                <label>Bio (max. 500 Zeichen)</label>
                <textarea name="bio" rows="5" maxlength="500" placeholder="Erzähl uns etwas über dich...">{bio}</textarea>
            </div>
            
            <div class="privacy-warning">
                <strong>⚠️ Datenschutz-Hinweis:</strong><br>
                Bitte gib <em>keine</em> privaten Daten an (echter Name, Adresse, Telefonnummer). Bio und Avatar sind öffentlich.
            </div>

            <div class="checkbox-group">
                <input type="checkbox" id="confirm" name="confirm" value="1" {checked_attr}>
                <label for="confirm">Ich habe verstanden, dass ich keine privaten Daten angeben soll.</label>
            </div>

            <div style="display:flex; gap:10px;">
                <button type="submit" class="btn">Profil speichern</button>
                <a href="/forum/profil/{_escape(username)}" class="btn" style="background:#21262d; color:#c9d1d9;">Abbrechen</a>
            </div>
        </form>
    </div>
    """


def render_profile_view(username: str, profile: dict = None) -> str:
    """Profil-Ansicht (öffentlich, 2026 Design)."""
    if profile is None:
        profile = get_user_profile(username) or {}
    bio = _escape(profile.get("bio", "")).replace("\n", "<br>") or "<em>Keine Bio vorhanden.</em>"
    avatar_url = profile.get("avatar_path", "")
    
    if avatar_url:
        avatar_html = f'<img src="{_escape(avatar_url)}" class="profile-avatar-large" alt="{_escape(username)}">'
    else:
        avatar_html = _avatar_html(username, size=100).replace('class="forum-avatar"', 'class="profile-avatar-large"')

    return f"""
    <div class="profile-container">
        <div class="profile-header">
            {avatar_html}
            <div>
                <h2 style="margin:0;">{_escape(username)}</h2>
                <p class="muted" style="margin:5px 0 0 0;">Mitglied seit {_fmt_time(profile.get("created_at", 0))}</p>
            </div>
        </div>
        <div>
            <h3 style="border-bottom:1px solid #30363d; padding-bottom:8px;">Über mich</h3>
            <p style="line-height:1.6;">{bio}</p>
        </div>
        <div style="margin-top:2em; padding-top:1em; border-top:1px solid #21262d;">
            <a href="/forum/profil/edit" class="btn">Profil bearbeiten</a>
            <a href="/forum" class="btn" style="background:#21262d; color:#c9d1d9;">← Zurück zum Forum</a>
        </div>
    </div>
    """


def render_not_found() -> str:
    return (
        "<p>Dieser Thread existiert nicht (mehr).</p>\n"
        "<a class=\"btn\" href=\"/forum\">← Zurück zum Forum</a>\n"
    )


def render_rate_limited(retry_after: int = 600) -> str:
    return (
        "<h1>Zu viele Aktionen</h1>\n"
        f"<p>Das Forum-Rate-Limit ist erreicht. Bitte warte "
        f"{retry_after // 60} Minuten.</p>\n"
        "<a class=\"btn\" href=\"/forum\">← Zurück zum Forum</a>\n"
    )


def render_admin_status(client_id: str = "", admin_token: str = "") -> str:
    st = rate_limit_status(client_id)
    return (
        "<h1>Admin-Status</h1>\n"
        f"<p>Client: <code>{_escape(st['client_id'])}</code></p>\n"
        "<p>Aktuelle Rate-Limit-Auslastung (pro Client):</p>\n"
        "<ul>\n"
        f"  <li>Neue Threads: {st['threads_used']} / {st['threads_max']}</li>\n"
        f"  <li>Antworten: {st['replies_used']} / {st['replies_max']}</li>\n"
        "</ul>\n"
        "<p>Global (Sicherheitsnetz):</p>\n"
        "<ul>\n"
        f"  <li>Neue Threads: {st['global_threads_used']} / {st['global_threads_max']}</li>\n"
        f"  <li>Antworten: {st['global_replies_used']} / {st['global_replies_max']}</li>\n"
        "</ul>\n"
        "<a class=\"btn\" href=\"/forum\">← Zurück zum Forum</a>\n"
        f"<a class=\"btn\" href=\"/forum/admin/authors?admin={_escape(admin_token)}\">Autoren</a>\n"
    )


def render_edit_form(thread: dict, index: int) -> str:
    posts = thread.get("posts", [])
    if index < 0 or index >= len(posts):
        return render_not_found()
    body_raw = posts[index].get("body", "")
    tid = _escape(thread["id"])
    return (
        f"<h1>Post bearbeiten</h1>\n"
        f"<p><a href=\"/forum/{tid}\">← Zurück zum Thread</a></p>\n"
        f"<form method=\"post\" action=\"/forum/{tid}/post/{index}/edit\">\n"
        f"  <p><label>Beitrag:<br>"
        f"<textarea name=\"body\" rows=\"10\" maxlength=\"4000\" required "
        f"style=\"width:100%\">{_escape(body_raw)}</textarea></label></p>\n"
        f"  <p><button type=\"submit\" class=\"btn\">Speichern</button></p>\n"
        f"</form>\n"
    )


def render_admin_authors(admin: bool = False, username: str = "") -> str:
    rows = ""
    # Mods sehen nur Autoren aus ihren Kategorien
    if not admin and username:
        from .forum_db import get_mod_categories, get_authors_in_categories
        mod_cats = get_mod_categories(username)
        authors = get_authors_in_categories(mod_cats)
    else:
        authors = list_authors()
    for author, count in authors:
        a = _escape(author)
        # Rolle des Autors
        role = "user"
        try:
            role = get_user_role(author)
        except Exception:
            pass
        role_badge = ""
        promote_btn = ""
        if role == "admin":
            role_badge = ' <span style="color:#ffaa33;font-weight:bold">[ADMIN]</span>'
            promote_btn = (
                f'<form method="post" action="/forum/admin/promote" style="display:inline">'
                f'<input type="hidden" name="username" value="{a}">'
                f'<input type="hidden" name="role" value="user">'
                f'<button type="submit" style="background:#666;color:#fff;border:none;'
                f'padding:0.2em 0.5em;border-radius:3px;cursor:pointer">→ User</button>'
                f'</form>'
            )
        elif role == "mod":
            role_badge = ' <span style="color:#ff3333;font-weight:bold">[MOD]</span>'
            promote_btn = (
                f'<form method="post" action="/forum/admin/promote" style="display:inline">'
                f'<input type="hidden" name="username" value="{a}">'
                f'<input type="hidden" name="role" value="user">'
                f'<button type="submit" style="background:#666;color:#fff;border:none;'
                f'padding:0.2em 0.5em;border-radius:3px;cursor:pointer">→ User</button>'
                f'</form>'
            )
        else:
            promote_btn = (
                f'<form method="post" action="/forum/admin/promote" style="display:inline">'
                f'<input type="hidden" name="username" value="{a}">'
                f'<input type="hidden" name="role" value="mod">'
                f'<button type="submit" style="background:#00aa66;color:#fff;border:none;'
                f'padding:0.2em 0.5em;border-radius:3px;cursor:pointer">→ Mod</button>'
                f'</form>'
            )
        rows += (
            f"<li><strong>{a}</strong>{role_badge} — {count} Post(s) "
            f"{promote_btn} "
            f"<form method=\"post\" action=\"/forum/admin/authors/delete\" "
            f"style=\"display:inline\">"
            f"<input type=\"hidden\" name=\"author\" value=\"{a}\">"
            f"<button type=\"submit\" "
            f"style=\"background:#c0392b;color:#fff;border:none;"
            f"padding:0.2em 0.5em;border-radius:3px;cursor:pointer\">"
            f"Alle Posts löschen</button></form></li>\n"
        )
    if not rows:
        rows = "<li><em>Noch keine Autoren.</em></li>"
    return (
        "<h1>Autoren-Verwaltung</h1>\n"
        '<p><a class="btn" href="/forum/admin/mods">→ Moderator-Verwaltung</a></p>\n'
        "<p>Alle Posts eines Autors thread-übergreifend löschen. "
        "Wenn der Eröffnungsbeitrag betroffen ist, wird der ganze Thread "
        "gelöscht.</p>\n"
        f"<ul>\n{rows}</ul>\n"
    )


def _pagination_html(page: int, pages: int, base_url: str, sort: str) -> str:
    """Baut Paginierungs-Links (Prev / Page X / Next)."""
    if pages <= 1:
        return ""
    parts = []
    if page > 1:
        parts.append(f"<a href=\"{base_url}?page={page-1}&sort={sort}\">← Zurück</a>")
    parts.append(f"<span>Seite {page} / {pages}</span>")
    if page < pages:
        parts.append(f"<a href=\"{base_url}?page={page+1}&sort={sort}\">Weiter →</a>")
    return "<p>" + " · ".join(parts) + "</p>\n"


def render_categories(client_id: str = "", username: str = "", admin: bool = False, mod: bool = False,
                      admin_token: str = "", base_address: str = "") -> str:
    cats = list_categories()
    status = rate_limit_status(client_id)
    client_status = (
        f"<p><small>Dein Limit: {status['threads_used']} / {status['threads_max']} "
        f"Threads, {status['replies_used']} / {status['replies_max']} Antworten "
        f"(Fenster: {status['window_seconds'] // 60} Minuten)</small></p>\n"
    )
    rows = ""
    cards_html = ""
    for c in cats:
        cid = _escape(c["id"])
        name = _escape(c["name"])
        desc = _escape(c["desc"])
        threads = c["threads_count"]
        posts = c["posts_count"]
        last_thread = c.get("last_thread")
        
        if last_thread:
            lt_title = _escape(last_thread.get("title", ""))
            lt_author = _escape(last_thread.get("author", ""))
            lt_time = _escape(last_thread.get("time", ""))
            last_info = (
                f'<div class="category-last">Letzter: '
                f'<a href="/forum/{cid}/thread/{last_thread.get("id", "")}">{lt_title}</a> '
                f'von {lt_author} ({lt_time})</div>'
            )
        else:
            last_info = '<div class="category-last muted">Kein Thread</div>'
            
        # ALLES (Info + Stats) befindet sich in der Karte!
        cards_html += f"""
        <a class="category-card" href="/forum/{cid}">
            <div class="category-info">
                <strong>{name}</strong>
                <div class="category-desc">{desc}</div>
                {last_info}
            </div>
            <div class="category-stats">
                <span>{threads} Threads</span><br>
                <span>{posts} Posts</span>
            </div>
        </a>
        """
    # Legende
    legend = (
        '<div class="legend">'
        '<strong>Legende:</strong> '
        '<span style="color:#ffaa33; font-weight:bold;">[ADMIN]</span> volle Rechte · '
        '<span style="color:#ff3333; font-weight:bold;">[MOD]</span> moderiert · '
        '<span style="color:#ff3333;">[USER]</span> schreibt · '
        '<span style="color:#888;">[GAST]</span> liest nur'
        '</div>'
    )

    # User-Navigation
    if username:
        # E-Mail-Adresse aus der verknuepften Identitaet
        user_email = ""
        try:
            user_email = get_user_email(username)
        except Exception:
            pass
        email_part = (
            f" (<code>{_escape(user_email)}</code>)" if user_email else ""
        )
        # Rolle anzeigen
        role = "user"
        try:
            role = get_user_role(username)
        except Exception:
            pass
        role_badge = ""
        if role == "admin":
            role_badge = ' <span style="color:#ffaa33; font-weight:bold;">[ADMIN]</span>'
        elif role == "mod":
            role_badge = ' <span style="color:#ff3333; font-weight:bold;">[MOD]</span>'
        user_nav = (
            f"<p>Eingeloggt als <strong>{_escape(username)}</strong>{role_badge}{email_part} · "
            f"<a href=\"/forum/my-threads\">Meine Threads</a> · "
            f"<a href=\"/forum/logout\">Logout</a></p>\n"
        )
    else:
        user_nav = (
            "<p><a href=\"/forum/login\">Login</a> · "
            "<a href=\"/forum/register\">Registrieren</a></p>\n"
        )

    admin_nav = ""
    if admin:
        open_reports = len(list_reports())
        reports_badge = (
            f" <strong style=\"color:#c0392b\">({open_reports} offen)</strong>"
            if open_reports > 0 else ""
        )
        if admin_token:
            suffix = "?admin=" + _escape(admin_token)
        else:
            suffix = ""
        admin_nav = (
            "<p><small>"
            f"<a href=\"/forum/admin/authors{suffix}\">Autoren</a> · "
            f"<a href=\"/forum/admin/reports{suffix}\">Meldungen{reports_badge}</a> · "
            f"<a href=\"/forum/admin/bans{suffix}\">Bans</a> · "
            f"<a href=\"/forum/admin/modlog{suffix}\">Mod-Log</a>"
            "</small></p>\n"
        )

    return (
        # Navbar oben
        '<header class="forum-header">'
        '  <div class="header-inner">'
        '    <a href="/forum" class="logo">EREBOS FORUM</a>'
        '    <nav class="top-nav">'
        '      <a href="/forum">Übersicht</a>'
        f'      <a href="{("http://wiki." + base_address + "/") if base_address else "/wiki"}">Wiki</a>'
        f'      <a href="{("http://mail." + base_address + "/") if base_address else "/mail"}">Mail</a>'
        f'      <a href="{("http://chat." + base_address + "/") if base_address else "/chat"}">Chat</a>'
        '    </nav>'
        '  </div>'
        '</header>'
        # Layout: Sidebar + Inhalt
        '<div class="forum-layout">'
        # Sidebar links
        '  <aside class="forum-sidebar">'
        '    <h3>Rubriken</h3>'
        '    <ul class="sidebar-nav">'
        f'      {rows}'
        '    </ul>'
        '  </aside>'
        # Hauptinhalt
        '  <main class="forum-main">'
        '    <p>Diskutiere mit anderen im Erebos-Netzwerk.</p>'
        f'    {legend}'
        f'    {user_nav}'
        f'    {client_status}'
        # Suchformular
        '    <form method="get" action="/forum/search" class="forum-search">'
        '      <input name="q" placeholder="Suche in Titeln und Posts...">'
        '      <button type="submit" class="btn">Suchen</button>'
        '    </form>'
        # Karten-Liste statt Tabelle
        '    <div class="category-list">'
        f'        {cards_html}'
        '    </div>'
        '    <a class="btn" href="/forum/neu">Neuen Thread erstellen</a>'
        f'    {admin_nav}'
        '    <a class="btn" href="/">← Startseite</a>'
        '  </main>'
        '</div>'
    )


def render_thread_list(category_id: str, page: int = 1,
                       sort: str = "active", admin: bool = False, mod: bool = False,
                       client_id: str = "") -> str:
    cat = get_category(category_id)
    if cat is None:
        return render_not_found()
    result = list_threads_paged(category_id=category_id, sort=sort, page=page)
    threads = result["threads"]
    items = ""
    if not threads:
        items = f"<li><em>Noch keine Threads in {_escape(cat['name'])}. " \
                f"<a href=\"/forum/neu?category={_escape(category_id)}\">" \
                f"Erstelle den ersten.</a></em></li>"
    else:
        for t in threads:
            tid = _escape(t["id"])
            title = _escape(t["title"])
            author = _escape(t["author"])
            replies = max(0, len(t.get("posts", [])) - 1)
            created = _fmt_time(t.get("created_at", 0))
            last = _fmt_time(t.get("last_activity", t.get("created_at", 0)))
            admin_btn = ""
            if admin:
                admin_btn = (
                    f" <form method=\"post\" action=\"/forum/{tid}/delete\" "
                    f"style=\"display:inline\"><button type=\"submit\" "
                    f"style=\"background:#c0392b;color:#fff;border:none;"
                    f"padding:0.2em 0.5em;border-radius:3px;cursor:pointer\">"
                    f"Löschen</button></form>"
                )
            avatar = _avatar_html_or_initials(t["author"], size=64)
            items += (
                f"<a class=\"thread-card\" href=\"/forum/{tid}\">\n"
                f"  {avatar}\n"
                f"  <div class=\"thread-info\">\n"
                f"    <strong>{title}</strong>\n"
                f"    <div class=\"thread-meta\">von {author} · {replies} Antwort(en) · "
                f"erstellt {created} · zuletzt aktiv {last}</div>\n"
                f"    {admin_btn}\n"
                f"  </div>\n"
                f"</a>\n"
            )
    sort_links = " · ".join(
        f"<a href=\"/forum/{_escape(category_id)}?sort={s}\""
        + (" style=\"font-weight:bold\"" if s == sort else "")
        + f">{label}</a>"
        for s, label in [("active", "Aktivität"), ("new", "Neu"), ("replies", "Antworten")]
    )
    pag_html = _pagination_html(
        result["page"], result["pages"], f"/forum/{_escape(category_id)}", sort
    )
    return (
        f"<p>{_escape(cat.get('desc', ''))}</p>\n"
        f"<p><small>Sortieren: {sort_links}</small></p>\n"
        f"<p><small>{result['total']} Thread(s), Seite {result['page']} / {result['pages']}</small></p>\n"
        f"<div class=\"thread-list\">\n{items}\n</div>\n"
        f"{pag_html}"
        f"<a class=\"btn\" href=\"/forum/neu?category={_escape(category_id)}\">"
        f"Neuen Thread in {_escape(cat['name'])}</a>\n"
        "<a class=\"btn\" href=\"/forum\">← Kategorien</a>\n"
    )


def render_search_results(query: str, results: list) -> str:
    q = _escape(query)
    if not results:
        return (
            "<p>Keine Treffer.</p>\n"
            "<a class=\"btn\" href=\"/forum\">← Zurück</a>\n"
        )
    items = ""
    for r in results:
        t = r["thread"]
        tid = _escape(t["id"])
        title = _escape(t["title"])
        cat = _escape(t.get("category_id", "allgemein"))
        items += f"<li><a href=\"/forum/{tid}\">{title}</a> <small>({cat})</small></li>\n"
    return (
        f"<p>{len(results)} Treffer.</p>\n"
        f"<ul>\n{items}\n</ul>\n"
        "<a class=\"btn\" href=\"/forum\">← Zurück</a>\n"
    )


def render_new_thread_form(category_id: str = "allgemein",
                            categories: Optional[list] = None) -> str:
    cats = categories or list_categories()
    options = "".join(
        f"<option value=\"{_escape(c['id'])}\""
        + (" selected" if c["id"] == category_id else "")
        + f">{_escape(c['name'])}</option>"
        for c in cats
    )
    return (
        "<h1>Neuen Thread erstellen</h1>\n"
        "<form method=\"post\" action=\"/forum/neu\">\n"
        f"  <p><label>Kategorie:<br><select name=\"category_id\" style=\"width:100%\">{options}</select></label></p>\n"
        "  <p><label>Titel:<br><input name=\"title\" maxlength=\"200\" required style=\"width:100%\"></label></p>\n"
        "  <p><label>Dein Name (optional):<br><input name=\"author\" maxlength=\"60\" placeholder=\"Anonym\" style=\"width:100%\"></label></p>\n"
        "  <p><label>Beitrag:<br><textarea name=\"body\" rows=\"8\" maxlength=\"4000\" required style=\"width:100%\"></textarea></label></p>\n"
        "  <p><button type=\"submit\" class=\"btn\">Thread erstellen</button></p>\n"
        "</form>\n"
        "<a class=\"btn\" href=\"/forum\">← Zurück zum Forum</a>\n"
    )


def render_login_form(error: str = "") -> str:
    err = f'<div class="form-error">{_escape(error)}</div>' if error else ""
    return f"""
    <div class="auth-page-wrapper">
        <div class="auth-container">
            {err}
            <form method="post" action="/forum/login" class="auth-form">
                <div class="form-group">
                    <label for="username">Benutzername</label>
                    <input type="text" id="username" name="username" required autocomplete="username" placeholder="Dein Benutzername">
                </div>
                <div class="form-group">
                    <label for="password">Passwort</label>
                    <input type="password" id="password" name="password" required autocomplete="current-password" placeholder="Dein Passwort">
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%; margin-top:1em;">Sicher einloggen</button>
            </form>
            <div class="auth-footer">
                <p>Noch kein Account? <a href="/forum/register">Jetzt registrieren</a></p>
                <a href="/forum" class="btn btn-secondary" style="margin-top:1em;">← Zurück zum Forum</a>
            </div>
        </div>
    </div>
    """

def render_register_form(error: str = "") -> str:
    err = f'<div class="form-error">{_escape(error)}</div>' if error else ""
    return f"""
    <div class="auth-page-wrapper">
        <div class="auth-container">
            {err}
            <div class="security-note">
                <strong>🔒 Maximale Privatsphäre:</strong> Dein Passwort wird lokal gehasht (PBKDF2). Wir speichern keine E-Mail-Adressen oder Tracking-Daten.
            </div>
            <form method="post" action="/forum/register" class="auth-form">
                <div class="form-group">
                    <label for="username">Benutzername</label>
                    <input type="text" id="username" name="username" required maxlength="32" autocomplete="username" placeholder="Wähle einen Benutzernamen">
                    <small class="muted">Maximal 32 Zeichen. Keine Leerzeichen.</small>
                </div>
                <div class="form-group">
                    <label for="password">Passwort</label>
                    <input type="password" id="password" name="password" required minlength="8" autocomplete="new-password" placeholder="Mindestens 8 Zeichen">
                    <small class="muted">Mindestens 8 Zeichen. Verwende eine Mischung aus Buchstaben, Zahlen und Sonderzeichen.</small>
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%; margin-top:1em;">Sicher registrieren</button>
            </form>
            <div class="auth-footer">
                <p>Bereits registriert? <a href="/forum/login">Hier einloggen</a></p>
                <a href="/forum" class="btn btn-secondary" style="margin-top:1em;">← Zurück zum Forum</a>
            </div>
        </div>
    </div>
    """


def render_my_threads(username: str) -> str:
    threads = list_user_threads(username)
    items = ""
    for t in threads:
        tid = _escape(t["id"])
        title = _escape(t["title"])
        cat = _escape(t.get("category_id", "allgemein"))
        items += f"<li><a href=\"/forum/{tid}\">{title}</a> <small>({cat})</small></li>\n"
    if not items:
        items = "<li><em>Du hast noch keine Threads.</em></li>"
    return (
        f"<h1>Meine Threads ({_escape(username)})</h1>\n"
        f"<ul>\n{items}\n</ul>\n"
        "<a class=\"btn\" href=\"/forum\">← Zurück zum Forum</a>\n"
    )


def render_report_form(thread_id: str, index: int) -> str:
    tid = _escape(thread_id)
    return (
        "<h1>Post melden</h1>\n"
        f"<form method=\"post\" action=\"/forum/{tid}/post/{index}/report\">\n"
        "  <p><label>Grund:<br><textarea name=\"reason\" rows=\"4\" maxlength=\"500\" required style=\"width:100%\"></textarea></label></p>\n"
        "  <p><button type=\"submit\" class=\"btn\">Melden</button></p>\n"
        "</form>\n"
        f"<a class=\"btn\" href=\"/forum/{tid}\">← Zurück</a>\n"
    )


def render_reports() -> str:
    reports = list_reports()
    items = ""
    for idx, r in enumerate(reports):
        tid = _escape(r["thread_id"])
        reason = _escape(r["reason"])
        reporter = _escape(r["reporter"])
        created = _fmt_time(r["created_at"])
        items += (
            f"<li>Thread <a href=\"/forum/{tid}\">{tid}</a>, "
            f"Post {r['post_index']} — {reason} (von {reporter}, {created}) "
            f"<form method=\"post\" action=\"/forum/admin/reports/{idx}/resolve\" style=\"display:inline\">"
            f"<button type=\"submit\" class=\"btn\" style=\"padding:0.1em 0.4em;font-size:0.8em\">Erledigt</button></form></li>\n"
        )
    if not items:
        items = "<li><em>Keine offenen Meldungen.</em></li>"
    return "<h1>Meldungen</h1>\n" + f"<ul>\n{items}\n</ul>\n"


def render_mod_log() -> str:
    log = list_mod_log(100)
    items = ""
    for e in log:
        items += (
            f"<li><small>{_fmt_time(e['created_at'])}</small> "
            f"<strong>{_escape(e['action'])}</strong> {_escape(e['target'])} "
            f"(von {_escape(e['moderator'])})</li>\n"
        )
    if not items:
        items = "<li><em>Noch keine Moderationseintraege.</em></li>"
    return "<h1>Moderations-Log</h1>\n" + f"<ul>\n{items}\n</ul>\n"


def render_health() -> str:
    data = load_forum()
    return (
        "<h1>Health</h1>\n"
        "<ul>\n"
        f"  <li>Threads: {len(data['threads'])}</li>\n"
        f"  <li>Users: {len(data.get('users', {}))}</li>\n"
        f"  <li>Offene Reports: {len(list_reports())}</li>\n"
        f"  <li>Bans: {len(data.get('bans', []))}</li>\n"
        f"  <li>Mod-Log: {len(data.get('mod_log', []))}</li>\n"
        "</ul>\n"
    )


def render_bans() -> str:
    data = load_forum()
    bans = data.get("bans", [])
    rows = ""
    for idx, b in enumerate(bans):
        username = _escape(b.get("username", "?"))
        reason = _escape(b.get("reason", ""))
        created = _fmt_time(b.get("created_at", 0))
        rows += (
            f"<li><strong>{username}</strong> — {reason} ({created}) "
            f"<form method=\"post\" action=\"/forum/admin/bans/{idx}/unban\" "
            f"style=\"display:inline\">"
            f"<button type=\"submit\" "
            f"style=\"background:#27ae60;color:#fff;border:none;"
            f"padding:0.2em 0.5em;border-radius:3px;cursor:pointer\">"
            f"Entbannen</button></form></li>\n"
        )
    if not rows:
        rows = "<li><em>Keine Bans.</em></li>"
    return (
        "<h1>Ban-Liste</h1>\n"
        "<form method=\"post\" action=\"/forum/admin/ban\">\n"
        "  <p><label>Username:<br><input name=\"username\" required style=\"width:100%\"></label></p>\n"
        "  <p><label>Grund:<br><input name=\"reason\" maxlength=\"500\" style=\"width:100%\"></label></p>\n"
        "  <p><button type=\"submit\" class=\"btn\">Bannen</button></p>\n"
        "</form>\n"
        f"<ul>\n{rows}\n</ul>\n"
    )


def unban_user(index: int) -> bool:
    data = load_forum()
    bans = data.get("bans", [])
    if index < 0 or index >= len(bans):
        return False
    del bans[index]
    return save_forum(data)


def render_quote_form(thread: dict, index: int) -> str:
    posts = thread.get("posts", [])
    if index < 0 or index >= len(posts):
        return render_not_found()
    author = _escape(posts[index].get("author", "?"))
    body_raw = posts[index].get("body", "")
    tid = _escape(thread["id"])
    quoted = f">>> {author} schrieb:\n\n{body_raw}\n\n"
    return (
        f"<h1>Zitat von {author}</h1>\n"
        f"<p><a href=\"/forum/{tid}\">← Zurück zum Thread</a></p>\n"
        f"<form method=\"post\" action=\"/forum/{tid}/antwort\">\n"
        f"  <p><label>Dein Name (optional):<br>"
        f"<input name=\"author\" maxlength=\"60\" placeholder=\"Anonym\" "
        f"style=\"width:100%\"></label></p>\n"
        f"  <p><label>Antwort (mit Zitat):<br>"
        f"<textarea name=\"body\" rows=\"10\" maxlength=\"4000\" required "
        f"style=\"width:100%\">{_escape(quoted)}</textarea></label></p>\n"
        f"  <p><button type=\"submit\" class=\"btn\">Antwort senden</button></p>\n"
        f"</form>\n"
    )


def render_mods_management(admin: bool = False) -> str:
    """Admin-UI: Mods Kategorien zuweisen."""
    if not admin:
        return "<h1>Nicht erlaubt</h1><p>Admin-Rechte erforderlich.</p>"

    from .forum_db import get_mods, get_mod_categories

    mods = get_mods()
    cats = list_categories()

    if not mods:
        return (
            "<h1>Moderator-Verwaltung</h1>\n"
            "<p><em>Noch keine Moderatoren. Weise zuerst jemandem die "
            "Rolle 'mod' zu (Autoren-Verwaltung).</em></p>\n"
            '<a class="btn" href="/forum/admin/authors">← Autoren-Verwaltung</a>\n'
        )

    rows = ""
    for mod in mods:
        current = get_mod_categories(mod)
        checkboxes = ""
        for cat in cats:
            checked = " checked" if cat["id"] in current else ""
            checkboxes += (
                '<label style="display:inline-block;margin:0.2em 0.5em;">'
                '<input type="checkbox" name="categories" value="'
                + _escape(cat["id"]) + '"' + checked + '> '
                + _escape(cat["name"]) + '</label>'
            )
        rows += (
            '<div style="border:1px solid #ff3333;padding:0.8em;margin:0.8em 0;'
            'border-radius:4px;">'
            '<p><strong>' + _escape(mod) + '</strong></p>'
            '<form method="post" action="/forum/admin/mods/set">'
            '<input type="hidden" name="username" value="' + _escape(mod) + '">'
            '<p>' + checkboxes + '</p>'
            '<p><button type="submit" class="btn">Speichern</button></p>'
            '</form>'
            '</div>'
        )

    return (
        "<h1>Moderator-Verwaltung</h1>\n"
        "<p>Weise jedem Moderator die Kategorien zu, in denen er/sie "
        "moderieren darf.</p>\n"
        + rows + '\n'
        '<a class="btn" href="/forum/admin/authors">← Autoren-Verwaltung</a>\n'
    )


def render_mods_set(username: str, category_ids: list, admin: bool = False) -> bytes:
    """POST /forum/admin/mods/set: Kategorien fuer einen Mod setzen."""
    if not admin:
        return b"REDIRECT:/forum"
    from .forum_db import set_mod_categories
    set_mod_categories(username, category_ids)
    log_moderation("mod_categories", f"{username} -> {len(category_ids)} Kategorien", "admin")
    return b"REDIRECT:/forum/admin/mods"
