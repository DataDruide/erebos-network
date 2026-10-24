"""HTML-Seiten fuer den Erebos Hidden-Service (Startseite + Wiki)."""

import json
import logging
from pathlib import Path
from typing import Optional

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


def render_page(path: str, address: str, request_line: str) -> bytes:
    if path == "/":
        return render_landing(address, request_line)
    if path == "/wiki":
        return render_wiki(address)
    return _page(
        "404 Nicht gefunden",
        address,
        "<h1>404 — Nicht gefunden</h1><p>Diese Seite existiert nicht.</p>"
        "<a class=\"btn\" href=\"/\">Zur Startseite</a>",
    )


def http_response(status: int, content_type: str, body: bytes) -> bytes:
    reason = {200: "OK", 404: "Not Found"}.get(status, "OK")
    return (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii") + body
