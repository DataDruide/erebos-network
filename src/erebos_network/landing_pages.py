"""HTML-Seiten fuer den Erebos Hidden-Service (Startseite + Wiki)."""

import json
import logging
from pathlib import Path
from typing import Optional

from . import forum

logger = logging.getLogger(__name__)

WIKI_PATH = Path("/app/wiki.json")


def parse_request_path(request: bytes) -> str:
    """Liest den Pfad aus der ersten HTTP-Zeile (z.B. 'GET /wiki HTTP/1.1')."""
    if not request:
        return "/"
    first_line = request.split(b"\r\n", 1)[0].decode("utf-8", "replace")
    parts = first_line.split(" ")
    if len(parts) < 2:
        return "/"
    target = parts[1]
    # Query-String abschneiden
    return target.split("?", 1)[0] or "/"


def _load_wiki_entries() -> list:
    """Laedt die Wiki-Eintraege aus /app/wiki.json (oder gibt [] zurueck)."""
    try:
        if WIKI_PATH.exists():
            data = json.loads(WIKI_PATH.read_text(encoding="utf-8"))
            return data.get("entries", [])
    except Exception as e:
        logger.warning(f"Wiki-JSON konnte nicht geladen werden: {e}")
    return []


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _page(title: str, address: str, body: str) -> bytes:
    html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"de\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        f"  <title>{_escape(title)}</title>\n"
        "  <style>\n"
        "    body { font-family: sans-serif; max-width: 720px; margin: 2em auto; padding: 1em; line-height: 1.6; }\n"
        "    code { background: #f0f0f0; padding: 0.2em 0.4em; }\n"
        "    h1 { color: #2c3e50; }\n"
        "    h2 { color: #34495e; margin-top: 1.5em; }\n"
        "    ul { padding-left: 1.4em; }\n"
        "    .btn { display: inline-block; margin-top: 1em; padding: 0.6em 1.2em; background: #2c3e50; color: #fff; text-decoration: none; border-radius: 4px; }\n"
        "    .btn:hover { background: #1a252f; }\n"
        "    .addr { font-size: 0.85em; color: #666; word-break: break-all; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        f"<p class=\"addr\"><strong>Diese Instanz:</strong> <code>{_escape(address)}</code></p>\n"
        "</body>\n"
        "</html>\n"
    )
    return html.encode("utf-8")


def render_landing(address: str, request_line: str) -> bytes:
    body = (
        "<h1>Willkommen im Erebos-Netzwerk</h1>\n"
        "<p>Du hast einen Hidden Service über das Erebos-Netzwerk erreicht.</p>\n"
        "<h2>Regeln</h2>\n"
        "<ul>\n"
        "  <li><strong>Respekt:</strong> Keine Angriffe auf andere Dienste, keine Belästigung.</li>\n"
        "  <li><strong>Keine illegalen Inhalte:</strong> Keine CSAM, keine Gewaltverherrlichung, keine Drogen-/Waffenhandels-Plattformen.</li>\n"
        "  <li><strong>Privatsphäre:</strong> Keine Deanonymisierungsversuche, keine Datensammlung über andere Nutzer.</li>\n"
        "  <li><strong>Kein Spam:</strong> Keine Massenwerbung, keine Flooding-Angriffe.</li>\n"
        "  <li><strong>Forschungsprototyp:</strong> Dies ist ein Experiment, keine Produktionsinfrastruktur. Keine Garantie auf Verfügbarkeit oder Anonymität.</li>\n"
        "</ul>\n"
        f"<p><em>Deine Anfrage:</em> <code>{_escape(request_line)}</code></p>\n"
        "<a class=\"btn\" href=\"/wiki\">Zur Hidden Wiki →</a>\n"
    )
    return _page("Willkommen bei Erebos", address, body)


def render_wiki(address: str) -> bytes:
    entries = _load_wiki_entries()
    items = []
    for e in entries:
        name = _escape(str(e.get("name", "?")))
        url = _escape(str(e.get("url", "#")))
        desc = _escape(str(e.get("desc", "")))
        items.append(
            f"<li><a href=\"{url}\">{name}</a> — {desc}<br><code>{url}</code></li>"
        )
    if not items:
        items.append("<li><em>Noch keine Einträge. Bearbeite wiki.json und mounte sie neu.</em></li>")
    body = (
        "<h1>Hidden Wiki</h1>\n"
        "<p>Eine Liste von Diensten im Erebos-Netzwerk. Platzhalter-Einträge, bis echte Dienste existieren.</p>\n"
        f"<ul>\n{chr(10).join(items)}\n</ul>\n"
        "<a class=\"btn\" href=\"/\">← Zurück zur Startseite</a>\n"
    )
    return _page("Hidden Wiki", address, body)


def render_page(path: str, address: str, request_line: str, method: str = "GET",
                body: bytes = b"", query: str = "", client_id: str = "") -> bytes:
    admin_token_value = ""
    if query:
        from urllib.parse import parse_qs
        q = parse_qs(query)
        admin_token_value = (q.get("admin", [""])[0] or "")
    admin = forum.is_admin(admin_token_value)

    if path == "/":
        return render_landing(address, request_line)
    if path == "/wiki":
        return render_wiki(address)
    if path == "/forum":
        return _page("Erebos Community", address, forum.render_categories(client_id=client_id))
    if path == "/forum/admin":
        if not admin:
            return _page(
                "Nicht erlaubt",
                address,
                "<h1>Nicht erlaubt</h1>"
                "<p>Admin-Token fehlt oder ist falsch.</p>"
                "<a class=\"btn\" href=\"/forum\">← Zurück</a>",
            )
        return _page("Admin", address, forum.render_admin_status(client_id=client_id))

    if path == "/forum/admin/authors":
        if not admin:
            return _page(
                "Nicht erlaubt", address,
                "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
            )
        return _page("Autoren", address, forum.render_admin_authors())

    if path == "/forum/admin/authors/delete" and method == "POST":
        if not admin:
            return _page(
                "Nicht erlaubt", address,
                "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
            )
        form = forum.parse_form_body(body)
        author = form.get("author", "")
        result = forum.delete_posts_by_author(author)
        logger.info(f"Admin: {author} -> {result}")
        return b"REDIRECT:/forum/admin/authors?admin=" + admin_token_value.encode("utf-8")
    if path == "/forum/search":
        from urllib.parse import parse_qs as _pq
        q = ""
        if query:
            q = (_pq(query).get("q", [""])[0] or "")
        results = forum.search_threads(q)
        return _page(f"Suche: {q}", address, forum.render_search_results(q, results))

    # /forum/<category>?page=N&sort=X (aber nicht /forum/neu, /forum/search, /forum/admin*, /forum/<id>)
    if (path.startswith("/forum/")
            and not path.startswith("/forum/neu")
            and not path.startswith("/forum/search")
            and not path.startswith("/forum/admin")
            and "/" not in path[len("/forum/"):]):
        cat_slug = path[len("/forum/"):]
        # Nur als Kategorie behandeln, wenn sie existiert
        if forum.get_category(cat_slug) is not None:
            from urllib.parse import parse_qs as _pq
            params = _pq(query) if query else {}
            page_n = 1
            sort = "active"
            try:
                page_n = int(params.get("page", ["1"])[0])
            except (ValueError, TypeError):
                page_n = 1
            sort = params.get("sort", ["active"])[0] or "active"
            return _page(
                forum.get_category(cat_slug)["name"],
                address,
                forum.render_thread_list(
                    cat_slug, page=page_n, sort=sort,
                    admin=admin, client_id=client_id,
                ),
            )

    if path == "/forum/neu":
        if method == "POST":
            form = forum.parse_form_body(body)
            tid = forum.create_thread(
                form.get("title", ""),
                form.get("author", ""),
                form.get("body", ""),
                client_id=client_id,
                category_id=form.get("category_id", "allgemein"),
            )
            if tid:
                return b"REDIRECT:" + f"/forum/{tid}".encode("utf-8")
            return _page(
                "Fehler",
                address,
                "<p>Thread konnte nicht erstellt werden "
                "(Titel und Beitrag erforderlich).</p>"
                + forum.render_new_thread_form(),
            )
        from urllib.parse import parse_qs as _pq
        cat_pre = "allgemein"
        if query:
            cat_pre = (_pq(query).get("category", ["allgemein"])[0] or "allgemein")
        return _page(
            "Neuer Thread", address,
            forum.render_new_thread_form(category_id=cat_pre),
        )
    if path.startswith("/forum/"):
        rest = path[len("/forum/"):]

        if rest.endswith("/antwort"):
            tid = rest[: -len("/antwort")]
            form = forum.parse_form_body(body)
            ok = forum.add_reply(tid, form.get("author", ""), form.get("body", ""), client_id=client_id)
            if not ok:
                return _page(
                    "Rate-Limit",
                    address,
                    forum.render_rate_limited(),
                )
            return b"REDIRECT:" + f"/forum/{tid}".encode("utf-8")

        if rest.endswith("/delete") and method == "POST":
            if not admin:
                return _page(
                    "Nicht erlaubt",
                    address,
                    "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
                )
            tid = rest[: -len("/delete")]
            forum.delete_thread(tid)
            return b"REDIRECT:/forum"

        # /forum/<id>/post/<idx>/delete
        if "/post/" in rest and rest.endswith("/delete") and method == "POST":
            if not admin:
                return _page(
                    "Nicht erlaubt",
                    address,
                    "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
                )
            head = rest[: -len("/delete")]
            tid, idx_str = head.split("/post/", 1)
            try:
                idx = int(idx_str)
            except ValueError:
                idx = -1
            forum.delete_post(tid, idx)
            return b"REDIRECT:" + f"/forum/{tid}".encode("utf-8")

        # /forum/<id>/post/<idx>/edit
        if "/post/" in rest and rest.endswith("/edit"):
            if not admin:
                return _page(
                    "Nicht erlaubt", address,
                    "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
                )
            head = rest[: -len("/edit")]
            tid, idx_str = head.split("/post/", 1)
            try:
                idx = int(idx_str)
            except ValueError:
                idx = -1
            t = forum.find_thread(tid)
            if t is None:
                return _page("Nicht gefunden", address, forum.render_not_found())
            if method == "POST":
                form = forum.parse_form_body(body)
                forum.edit_post(tid, idx, form.get("body", ""))
                return b"REDIRECT:" + f"/forum/{tid}".encode("utf-8")
            return _page("Bearbeiten", address, forum.render_edit_form(t, idx))

        t = forum.find_thread(rest)
        if t is None:
            return _page("Nicht gefunden", address, forum.render_not_found())
        return _page(t["title"], address, forum.render_thread(t, admin=admin))
    return _page(
        "404 Nicht gefunden",
        address,
        "<h1>404 — Nicht gefunden</h1><p>Diese Seite existiert nicht.</p>"
        "<a class=\"btn\" href=\"/\">Zur Startseite</a>",
    )


def http_response(status: int, content_type: str, body: bytes,
                  location: str = "", set_cookie: str = "") -> bytes:
    reason = {200: "OK", 302: "Found", 404: "Not Found"}.get(status, "OK")
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
    )
    if location:
        headers += f"Location: {location}\r\n"
    if set_cookie:
        headers += f"Set-Cookie: {set_cookie}\r\n"
    headers += "Connection: close\r\n\r\n"
    return headers.encode("ascii") + body


def parse_http_request(data: bytes) -> tuple:
    """Parst einen rohen HTTP-Request.

    Returns:
        (method, path, headers_dict, body_bytes)
    """
    if not data:
        return ("GET", "/", {}, b"")
    if b"\r\n\r\n" in data:
        head, body = data.split(b"\r\n\r\n", 1)
    else:
        head, body = data, b""
    lines = head.split(b"\r\n")
    if not lines:
        return ("GET", "/", {}, b"")
    request_line = lines[0].decode("utf-8", "replace")
    parts = request_line.split(" ")
    method = parts[0] if parts else "GET"
    target = parts[1] if len(parts) > 1 else "/"
    path = target.split("?", 1)[0] or "/"
    headers = {}
    for line in lines[1:]:
        if b":" in line:
            k, v = line.split(b":", 1)
            headers[k.decode("ascii", "replace").strip().lower()] = v.decode(
                "utf-8", "replace"
            ).strip()
    return (method, path, headers, body)
