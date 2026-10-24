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
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)

FORUM_PATH = Path("/app/forum.json")
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
PBKDF2_ITERATIONS = 200_000
MIN_PASSWORD_LEN = 8
MAX_USERNAME_LEN = 32
SESSION_TTL_SECONDS = 7 * 24 * 3600  # 7 Tage

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


def login_user(username: str, password: str) -> Optional[str]:
    """Prueft Login. Liefert session_token (oder None)."""
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
        return None
    try:
        expected = bytes.fromhex(user["password_hash"])
        salt = bytes.fromhex(user["salt"])
    except (KeyError, ValueError):
        return None
    if not _verify_password(password, expected, salt):
        return None
    token = secrets.token_urlsafe(32)
    data["sessions"][token] = {
        "username": user["username"],
        "created_at": time.time(),
        "expires_at": time.time() + SESSION_TTL_SECONDS,
    }
    save_forum(data)
    return token


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


def is_admin(token: Optional[str]) -> bool:
    return bool(token) and token == admin_token()


def _ensure_structure(data: dict) -> dict:
    """Stellt sicher, dass admin_token, rate_log, categories vorhanden sind."""
    if "admin_token" not in data:
        data["admin_token"] = admin_token()
    if "categories" not in data:
        data["categories"] = list(DEFAULT_CATEGORIES)
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
    """Laedt die Forum-Daten aus FORUM_PATH (oder initialisiert leer)."""
    try:
        if FORUM_PATH.exists():
            data = json.loads(FORUM_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "threads" in data:
                return _ensure_structure(data)
    except Exception as e:
        logger.warning(f"Forum-JSON konnte nicht geladen werden: {e}")
    return _ensure_structure({"threads": []})


def save_forum(data: dict) -> bool:
    """Schreibt die Forum-Daten nach FORUM_PATH.

    Hinweis: Direkt-Schreiben (kein tmp+rename), weil forum.json als
    Docker-Bind-Mount eingehaengt ist. rename() ueber die Mount-Grenze
    hinweg schlaegt mit EXDEV/EBUSY fehl (macOS Docker Desktop).
    """
    try:
        FORUM_PATH.parent.mkdir(parents=True, exist_ok=True)
        FORUM_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception as e:
        logger.error(f"Forum-JSON konnte nicht geschrieben werden: {e}")
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
    """Liefert Kategorien mit Thread- und Post-Zaehler."""
    data = load_forum()
    result = []
    for c in data.get("categories", []):
        cid = c["id"]
        threads = [t for t in data["threads"] if t.get("category_id") == cid]
        posts_count = sum(len(t.get("posts", [])) for t in threads)
        result.append({
            "id": cid,
            "name": c["name"],
            "desc": c.get("desc", ""),
            "threads_count": len(threads),
            "posts_count": posts_count,
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


def render_markdown(text: str) -> str:
    """Sicheres Markdown-Mini: **bold**, *italic*, `code`, [text](url)."""
    escaped = _escape(text).replace("\n", "<br>")
    # Links: nur http(s)
    def _link(m):
        label, url = m.group(1), m.group(2)
        return f'<a href="{url}" rel="noopener">{label}</a>'
    escaped = _MD_LINK.sub(_link, escaped)
    escaped = _MD_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", escaped)
    escaped = _MD_BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = _MD_ITALIC.sub(r"<em>\1</em>", escaped)
    return escaped


def list_user_threads(username: str) -> list:
    data = load_forum()
    return [
        t for t in data["threads"]
        if any(p.get("author") == username for p in t.get("posts", []))
    ]


def report_post(thread_id: str, index: int, reason: str, reporter: str = "") -> bool:
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
            if admin:
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
        "<h1>Forum</h1>\n"
        "<p>Diskutiere mit anderen im Erebos-Netzwerk.</p>\n"
        f"{client_status}"
        f"<ul>\n{items}\n</ul>\n"
        "<a class=\"btn\" href=\"/forum/neu\">Neuen Thread erstellen</a>\n"
        "<a class=\"btn\" href=\"/\">← Startseite</a>\n"
    )





def render_thread(thread: dict, admin: bool = False) -> str:
    tid = _escape(thread["id"])
    title = _escape(thread["title"])
    posts_html = ""
    for idx, p in enumerate(thread.get("posts", [])):
        author = _escape(p.get("author", "?"))
        body = render_markdown(p.get("body", ""))
        created = _fmt_time(p.get("created_at", 0))
        edited = p.get("edited_at")
        edited_marker = ""
        if edited:
            edited_marker = f" <small><em>(bearbeitet {_fmt_time(edited)})</em></small>"
        admin_btn = ""
        if admin:
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
        # Zitat-Button
        quote_btn = (
            f" <a href=\"#quote\" onclick=\"document.querySelector('textarea[name=body]').value="
            f"'>>> {author} schrieb:\\n\\n';return false;\" "
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
        posts_html += (
            f"<div style=\"border:1px solid #ddd;padding:0.8em;margin:0.8em 0;border-radius:4px\">\n"
            f"  <p><strong>{author}</strong> <small>{created}</small>{edited_marker}"
            f"{quote_btn}{report_btn}{ban_btn}{admin_btn}</p>\n"
            f"  <p>{body}</p>\n"
            f"</div>\n"
        )
    sticky_locked = ""
    if thread.get("sticky"):
        sticky_locked += " <small>[sticky]</small>"
    if thread.get("locked"):
        sticky_locked += " <small>[gesperrt]</small>"
    if admin:
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
    return (
        f"<h1>{title}{sticky_locked}</h1>\n"
        f"<p><a href=\"/forum\">← Zurück zum Forum</a></p>\n"
        f"{posts_html}\n"
        f"{reply_block}"
    )


def render_not_found() -> str:
    return (
        "<h1>Thread nicht gefunden</h1>\n"
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


def render_admin_status(client_id: str = "") -> str:
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
        "<a class=\"btn\" href=\"/forum/admin/authors?admin=<token>\">Autoren</a>\n"
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


def render_admin_authors() -> str:
    rows = ""
    for author, count in list_authors():
        a = _escape(author)
        rows += (
            f"<li><strong>{a}</strong> — {count} Post(s) "
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


def render_categories(client_id: str = "", username: str = "", admin: bool = False) -> str:
    cats = list_categories()
    status = rate_limit_status(client_id)
    client_status = (
        f"<p><small>Dein Limit: {status['threads_used']} / {status['threads_max']} "
        f"Threads, {status['replies_used']} / {status['replies_max']} Antworten "
        f"(Fenster: {status['window_seconds'] // 60} Minuten)</small></p>\n"
    )
    rows = ""
    for c in cats:
        cid = _escape(c["id"])
        name = _escape(c["name"])
        desc = _escape(c["desc"])
        rows += (
            f"<li><a href=\"/forum/{cid}\">{name}</a> "
            f"<small>{c['threads_count']} Thread(s), "
            f"{c['posts_count']} Post(s) — {desc}</small></li>\n"
        )
    if not rows:
        rows = "<li><em>Noch keine Kategorien.</em></li>"

    # User-Navigation
    if username:
        user_nav = (
            f"<p>Eingeloggt als <strong>{_escape(username)}</strong> · "
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
        admin_nav = (
            "<p><small>"
            "<a href=\"/forum/admin/authors?admin=<token>\">Autoren</a> · "
            f"<a href=\"/forum/admin/reports?admin=<token>\">Meldungen{reports_badge}</a> · "
            "<a href=\"/forum/admin/bans?admin=<token>\">Bans</a> · "
            "<a href=\"/forum/admin/modlog?admin=<token>\">Mod-Log</a>"
            "</small></p>\n"
        )

    return (
        "<h1>Erebos Community</h1>\n"
        "<p>Diskutiere mit anderen im Erebos-Netzwerk.</p>\n"
        f"{user_nav}"
        f"{client_status}"
        "<form method=\"get\" action=\"/forum/search\" style=\"margin:1em 0\">\n"
        "  <input name=\"q\" placeholder=\"Suche in Titeln und Posts...\" "
        "style=\"width:70%;padding:0.4em\"> "
        "<button type=\"submit\" class=\"btn\">Suchen</button>\n"
        "</form>\n"
        f"<ul>\n{rows}</ul>\n"
        "<a class=\"btn\" href=\"/forum/neu\">Neuen Thread erstellen</a>\n"
        f"{admin_nav}"
        "<a class=\"btn\" href=\"/\">← Startseite</a>\n"
    )


def render_thread_list(category_id: str, page: int = 1,
                       sort: str = "active", admin: bool = False,
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
            items += (
                f"<li><a href=\"/forum/{tid}\">{title}</a> "
                f"<small>von {author} · {replies} Antwort(en) · "
                f"erstellt {created} · zuletzt aktiv {last}</small>"
                f"{admin_btn}</li>\n"
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
        f"<h1>{_escape(cat['name'])}</h1>\n"
        f"<p>{_escape(cat.get('desc', ''))}</p>\n"
        f"<p><small>Sortieren: {sort_links}</small></p>\n"
        f"<p><small>{result['total']} Thread(s), Seite {result['page']} / {result['pages']}</small></p>\n"
        f"<ul>\n{items}\n</ul>\n"
        f"{pag_html}"
        f"<a class=\"btn\" href=\"/forum/neu?category={_escape(category_id)}\">"
        f"Neuen Thread in {_escape(cat['name'])}</a>\n"
        "<a class=\"btn\" href=\"/forum\">← Kategorien</a>\n"
    )


def render_search_results(query: str, results: list) -> str:
    q = _escape(query)
    if not results:
        return (
            f"<h1>Suche: {q}</h1>\n"
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
        f"<h1>Suche: {q}</h1>\n"
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
    err = f"<p style=\"color:#c0392b\">{_escape(error)}</p>" if error else ""
    return (
        "<h1>Login</h1>\n"
        f"{err}"
        "<form method=\"post\" action=\"/forum/login\">\n"
        "  <p><label>Username:<br><input name=\"username\" required style=\"width:100%\"></label></p>\n"
        "  <p><label>Passwort:<br><input type=\"password\" name=\"password\" required style=\"width:100%\"></label></p>\n"
        "  <p><button type=\"submit\" class=\"btn\">Login</button></p>\n"
        "</form>\n"
        "<p><a href=\"/forum/register\">Noch kein Account? Registrieren</a></p>\n"
        "<a class=\"btn\" href=\"/forum\">← Zurück zum Forum</a>\n"
    )


def render_register_form(error: str = "") -> str:
    err = f"<p style=\"color:#c0392b\">{_escape(error)}</p>" if error else ""
    return (
        "<h1>Registrieren</h1>\n"
        f"{err}"
        "<form method=\"post\" action=\"/forum/register\">\n"
        "  <p><label>Username:<br><input name=\"username\" required maxlength=\"32\" style=\"width:100%\"></label></p>\n"
        "  <p><label>Passwort (min. 8 Zeichen):<br><input type=\"password\" name=\"password\" required minlength=\"8\" style=\"width:100%\"></label></p>\n"
        "  <p><button type=\"submit\" class=\"btn\">Account erstellen</button></p>\n"
        "</form>\n"
        "<a class=\"btn\" href=\"/forum\">← Zurück zum Forum</a>\n"
    )


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
