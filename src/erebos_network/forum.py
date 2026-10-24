"""Einfaches Forum fuer den Erebos Hidden-Service (JSON-persistent)."""

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

# Standard-Kategorien (werden beim ersten Start angelegt)
DEFAULT_CATEGORIES = [
    {"id": "allgemein", "name": "Allgemein", "desc": "Allgemeine Diskussionen"},
    {"id": "technik", "name": "Technik", "desc": "Erebos, Krypto, Netzwerk"},
    {"id": "support", "name": "Support", "desc": "Hilfe und Fragen"},
    {"id": "offtopic", "name": "Off-Topic", "desc": "Alles andere"},
]
THREADS_PER_PAGE = 20


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
    for t in data["threads"]:
        if t["id"] == thread_id:
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
        body = _escape(p.get("body", "")).replace("\n", "<br>")
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
        posts_html += (
            f"<div style=\"border:1px solid #ddd;padding:0.8em;margin:0.8em 0;border-radius:4px\">\n"
            f"  <p><strong>{author}</strong> <small>{created}</small>{edited_marker}{admin_btn}</p>\n"
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


def render_categories(client_id: str = "") -> str:
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
    return (
        "<h1>Erebos Community</h1>\n"
        "<p>Diskutiere mit anderen im Erebos-Netzwerk.</p>\n"
        f"{client_status}"
        "<form method=\"get\" action=\"/forum/search\" style=\"margin:1em 0\">\n"
        "  <input name=\"q\" placeholder=\"Suche in Titeln und Posts...\" "
        "style=\"width:70%;padding:0.4em\"> "
        "<button type=\"submit\" class=\"btn\">Suchen</button>\n"
        "</form>\n"
        f"<ul>\n{rows}</ul>\n"
        "<a class=\"btn\" href=\"/forum/neu\">Neuen Thread erstellen</a>\n"
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
