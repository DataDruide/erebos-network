"""Einfaches Forum fuer den Erebos Hidden-Service (JSON-persistent)."""

import json
import logging
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
                return data
    except Exception as e:
        logger.warning(f"Forum-JSON konnte nicht geladen werden: {e}")
    return {"threads": []}


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
    for t in data["threads"]:
        if t["id"] == thread_id:
            t["posts"].append({
                "author": author,
                "body": body,
                "created_at": time.time(),
            })
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

def render_forum_list() -> str:
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
            items += (
                f"<li><a href=\"/forum/{tid}\">{title}</a> "
                f"<small>von {author} · {replies} Antwort(en) · {created}</small></li>\n"
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


def render_thread(thread: dict) -> str:
    tid = _escape(thread["id"])
    title = _escape(thread["title"])
    posts_html = ""
    for p in thread.get("posts", []):
        author = _escape(p.get("author", "?"))
        body = _escape(p.get("body", "")).replace("\n", "<br>")
        created = _fmt_time(p.get("created_at", 0))
        posts_html += (
            f"<div style=\"border:1px solid #ddd;padding:0.8em;margin:0.8em 0;border-radius:4px\">\n"
            f"  <p><strong>{author}</strong> <small>{created}</small></p>\n"
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
