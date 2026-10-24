"""Einfaches Forum fuer den Erebos Hidden-Service (JSON-persistent)."""

import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)

FORUM_PATH = Path("/app/forum.json")
MAX_TITLE = 200
MAX_AUTHOR = 60
MAX_BODY = 4000

# Rate-Limit: max. N Aktionen pro Zeitfenster (global, nicht pro Client).
RATE_WINDOW_SECONDS = 600  # 10 Minuten
RATE_MAX_THREADS = 10      # neue Threads pro Fenster
RATE_MAX_REPLIES = 30      # Antworten pro Fenster


def admin_token() -> str:
    """Admin-Token aus Env (Default 'changeme')."""
    return os.environ.get("EREBOS_FORUM_ADMIN_TOKEN", "changeme")


def is_admin(token: Optional[str]) -> bool:
    return bool(token) and token == admin_token()


def _ensure_structure(data: dict) -> dict:
    """Stellt sicher, dass admin_token und rate_log vorhanden sind."""
    if "admin_token" not in data:
        # Wird nicht zum Pruefen genutzt (Env gewinnt), aber dokumentiert
        # den Wert in der JSON-Datei.
        data["admin_token"] = admin_token()
    if "rate_log" not in data:
        data["rate_log"] = {"threads": [], "replies": []}
    else:
        data["rate_log"].setdefault("threads", [])
        data["rate_log"].setdefault("replies", [])
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


def create_thread(title: str, author: str, body: str) -> Optional[str]:
    """Legt einen neuen Thread an. Gibt die Thread-ID zurueck (oder None)."""
    title = _clean(title, MAX_TITLE)
    body = _clean(body, MAX_BODY)
    author = _clean(author, MAX_AUTHOR) or "Anonym"
    if not title or not body:
        return None
    data = load_forum()
    if not _check_rate(data, "threads"):
        logger.warning("Rate-Limit erreicht: zu viele neue Threads")
        return None
    thread_id = secrets.token_hex(6)
    now = time.time()
    data["threads"].insert(0, {
        "id": thread_id,
        "title": title,
        "author": author,
        "created_at": now,
        "posts": [{
            "author": author,
            "body": body,
            "created_at": now,
        }],
    })
    _record_action(data, "threads")
    if save_forum(data):
        return thread_id
    return None


def add_reply(thread_id: str, author: str, body: str) -> bool:
    """Fuegt einem Thread eine Antwort hinzu."""
    body = _clean(body, MAX_BODY)
    author = _clean(author, MAX_AUTHOR) or "Anonym"
    if not body:
        return False
    data = load_forum()
    if not _check_rate(data, "replies"):
        logger.warning("Rate-Limit erreicht: zu viele Antworten")
        return False
    for t in data["threads"]:
        if t["id"] == thread_id:
            t["posts"].append({
                "author": author,
                "body": body,
                "created_at": time.time(),
            })
            _record_action(data, "replies")
            return save_forum(data)
    return False


def _check_rate(data: dict, kind: str) -> bool:
    """Prueft das Rate-Limit. True = erlaubt, False = geblockt."""
    now = time.time()
    log = data["rate_log"]
    # Alte Eintraege (> RATE_WINDOW_SECONDS) entfernen
    log[kind] = [t for t in log[kind] if now - t < RATE_WINDOW_SECONDS]
    max_allowed = RATE_MAX_THREADS if kind == "threads" else RATE_MAX_REPLIES
    return len(log[kind]) < max_allowed


def _record_action(data: dict, kind: str) -> None:
    data["rate_log"][kind].append(time.time())


def rate_limit_status() -> dict:
    """Liefert den aktuellen Stand (fuer Doku/Tests)."""
    data = load_forum()
    now = time.time()
    threads = [t for t in data["rate_log"]["threads"] if now - t < RATE_WINDOW_SECONDS]
    replies = [t for t in data["rate_log"]["replies"] if now - t < RATE_WINDOW_SECONDS]
    return {
        "threads_used": len(threads),
        "threads_max": RATE_MAX_THREADS,
        "replies_used": len(replies),
        "replies_max": RATE_MAX_REPLIES,
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

def render_forum_list(admin: bool = False) -> str:
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
    return (
        "<h1>Forum</h1>\n"
        "<p>Diskutiere mit anderen im Erebos-Netzwerk.</p>\n"
        f"<ul>\n{items}\n</ul>\n"
        "<a class=\"btn\" href=\"/forum/neu\">Neuen Thread erstellen</a>\n"
        "<a class=\"btn\" href=\"/\">← Startseite</a>\n"
    )


def render_new_thread_form() -> str:
    return (
        "<h1>Neuen Thread erstellen</h1>\n"
        "<form method=\"post\" action=\"/forum/neu\">\n"
        "  <p><label>Titel:<br><input name=\"title\" maxlength=\"200\" required style=\"width:100%\"></label></p>\n"
        "  <p><label>Dein Name (optional):<br><input name=\"author\" maxlength=\"60\" placeholder=\"Anonym\" style=\"width:100%\"></label></p>\n"
        "  <p><label>Beitrag:<br><textarea name=\"body\" rows=\"8\" maxlength=\"4000\" required style=\"width:100%\"></textarea></label></p>\n"
        "  <p><button type=\"submit\" class=\"btn\">Thread erstellen</button></p>\n"
        "</form>\n"
        "<a class=\"btn\" href=\"/forum\">← Zurück zum Forum</a>\n"
    )


def render_thread(thread: dict, admin: bool = False) -> str:
    tid = _escape(thread["id"])
    title = _escape(thread["title"])
    posts_html = ""
    for idx, p in enumerate(thread.get("posts", [])):
        author = _escape(p.get("author", "?"))
        body = _escape(p.get("body", "")).replace("\n", "<br>")
        created = _fmt_time(p.get("created_at", 0))
        admin_btn = ""
        if admin:
            label = "Thread löschen" if idx == 0 else "Post löschen"
            admin_btn = (
                f" <form method=\"post\" action=\"/forum/{tid}/post/{idx}/delete\" "
                f"style=\"display:inline\"><button type=\"submit\" "
                f"style=\"background:#c0392b;color:#fff;border:none;"
                f"padding:0.2em 0.5em;border-radius:3px;cursor:pointer\">"
                f"{label}</button></form>"
            )
        posts_html += (
            f"<div style=\"border:1px solid #ddd;padding:0.8em;margin:0.8em 0;border-radius:4px\">\n"
            f"  <p><strong>{author}</strong> <small>{created}</small>{admin_btn}</p>\n"
            f"  <p>{body}</p>\n"
            f"</div>\n"
        )
    return (
        f"<h1>{title}</h1>\n"
        f"<p><a href=\"/forum\">← Zurück zum Forum</a></p>\n"
        f"{posts_html}\n"
        "<h2>Antworten</h2>\n"
        f"<form method=\"post\" action=\"/forum/{tid}/antwort\">\n"
        "  <p><label>Dein Name (optional):<br><input name=\"author\" maxlength=\"60\" placeholder=\"Anonym\" style=\"width:100%\"></label></p>\n"
        "  <p><label>Antwort:<br><textarea name=\"body\" rows=\"6\" maxlength=\"4000\" required style=\"width:100%\"></textarea></label></p>\n"
        "  <p><button type=\"submit\" class=\"btn\">Antwort senden</button></p>\n"
        "</form>\n"
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


def render_admin_status() -> str:
    st = rate_limit_status()
    return (
        "<h1>Admin-Status</h1>\n"
        "<p>Aktuelle Rate-Limit-Auslastung:</p>\n"
        "<ul>\n"
        f"  <li>Neue Threads: {st['threads_used']} / {st['threads_max']} "
        f"(Fenster: {st['window_seconds']}s)</li>\n"
        f"  <li>Antworten: {st['replies_used']} / {st['replies_max']}</li>\n"
        "</ul>\n"
        "<a class=\"btn\" href=\"/forum\">← Zurück zum Forum</a>\n"
    )
