"""Onboarding-Seiten: Startseite, Regeln, Wiki.

Enthaelt:
- render_welcome(): Startseite mit UUID, Diensten, Status
- render_landing(): Regeln-Seite
- render_wiki(): Hidden Wiki
"""

import hashlib as _hashlib
import json
import uuid as _uuid
from pathlib import Path

from .renderers import _page, _escape, _render_identity_box


WIKI_PATH = Path("/app/wiki.json")


def _load_wiki_entries() -> list:
    """Laedt die Wiki-Eintraege aus /app/wiki.json (oder gibt [] zurueck)."""
    try:
        if WIKI_PATH.exists():
            data = json.loads(WIKI_PATH.read_text(encoding="utf-8"))
            return data.get("entries", [])
    except Exception:
        pass
    return []


def render_welcome(address: str, client_id: str, request_line: str) -> bytes:
    """Anonyme Begruessungsseite: UUID, Dienste, Status auf einen Blick."""
    # Anonyme UUID aus client_id ableiten (deterministisch, nicht rueckfuehrbar)
    if client_id:
        anon_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))
    else:
        anon_uuid = str(_uuid.uuid4())

    short_id = anon_uuid[:8]

    body = (
        "<h1>Willkommen im Erebos-Netzwerk</h1>\n"
        "<p>Du bist anonym verbunden. Diese Seite zeigt dir alles auf einen Blick.</p>\n"
        "<h2>Deine anonyme Kennung</h2>\n"
        f"<p><code>{_escape(anon_uuid)}</code></p>\n"
        f"<p><small>Kurz-ID: <strong>#{_escape(short_id)}</strong> · "
        "Diese Kennung ist nur fuer diese Verbindung gueltig und nicht "
        "rueckfuehrbar auf deine IP oder Person.</small></p>\n"
        "<h2>Verbindung</h2>\n"
        "<ul>\n"
        "  <li><strong>Status:</strong> Verbunden ueber Erebos-Netzwerk</li>\n"
        "  <li><strong>Verschluesselung:</strong> Ende-zu-Ende (X25519 + ML-KEM-1024 + ChaCha20-Poly1305)</li>\n"
        "  <li><strong>Routing:</strong> 3-Hop-Onion (Proxy &rarr; peer2 &rarr; peer3 &rarr; peer1 &rarr; Hidden Service)</li>\n"
        "  <li><strong>Deine IP:</strong> fuer den Hidden Service nicht sichtbar</li>\n"
        "</ul>\n"
        "<h2>Verfuegbare Dienste</h2>\n"
        "<ul>\n"
        "  <li><a href=\"/mail\"><strong>Mail</strong></a> — anonyme Nachrichten (UUID-basiert)</li>\n"
        "  <li><a href=\"/wiki\"><strong>Hidden Wiki</strong></a> — Verzeichnis der Dienste</li>\n"
        "  <li><a href=\"/forum\"><strong>Erebos Community</strong></a> — Forum mit Threads und Antworten</li>\n"
        "  <li><a href=\"/regeln\"><strong>Regeln</strong></a> — was hier erlaubt ist und was nicht</li>\n"
        "  <li><a href=\"/forum/health\"><strong>Health</strong></a> — Status des Dienstes</li>\n"
        "</ul>\n"
        "<p style=\"margin-top:1.5em; padding:1em; background:#f9f9f9; "
        "border-left:4px solid #00aa00;\">\n"
        "  <strong>Schon eine Identitaet?</strong>\n"
        "  <a href=\"/recover\">Identitaet wiederherstellen</a>\n"
        "  (UUID oder E-Mail eingeben)\n"
        "</p>\n"
        "<h2>Deine Rechte</h2>\n"
        "<ul>\n"
        "  <li>Kein Login, kein Passwort, keine E-Mail-Adresse noetig.</li>\n"
        "  <li>Keine personenbezogenen Daten werden gespeichert.</li>\n"
        "  <li>Deine IP ist fuer den Hidden Service nicht sichtbar.</li>\n"
        "  <li>Der Inhalt deiner Anfragen ist Ende-zu-Ende verschluesselt.</li>\n"
        "</ul>\n"
        f"<p><em>Deine Anfrage:</em> <code>{_escape(request_line)}</code></p>\n"
        f"<p><small>Hidden-Service-Adresse: <code>{_escape(address)}</code></small></p>\n"
        "<a class=\"btn\" href=\"/wiki\">Zur Hidden Wiki &rarr;</a>\n"
        "<a class=\"btn\" href=\"/forum\">Zum Forum &rarr;</a>\n"
        "<a class=\"btn\" href=\"/regeln\">Zu den Regeln &rarr;</a>\n"
    )
    return _page("Willkommen bei Erebos", address, body)


def render_landing(address: str, request_line: str) -> bytes:
    body = (
        "<h1>Willkommen im Erebos-Netzwerk</h1>\n"
        "<p>Du hast einen Hidden Service \u00fcber das Erebos-Netzwerk erreicht.</p>\n"
        "<h2>Regeln</h2>\n"
        "<ul>\n"
        "  <li><strong>Respekt:</strong> Keine Angriffe auf andere Dienste, keine Bel\u00e4stigung.</li>\n"
        "  <li><strong>Keine illegalen Inhalte:</strong> Keine CSAM, keine Gewaltverherrlichung, keine Drogen-/Waffenhandels-Plattformen.</li>\n"
        "  <li><strong>Privatsph\u00e4re:</strong> Keine Deanonymisierungsversuche, keine Datensammlung \u00fcber andere Nutzer.</li>\n"
        "  <li><strong>Kein Spam:</strong> Keine Massenwerbung, keine Flooding-Angriffe.</li>\n"
        "  <li><strong>Forschungsprototyp:</strong> Dies ist ein Experiment, keine Produktionsinfrastruktur. Keine Garantie auf Verf\u00fcgbarkeit oder Anonymit\u00e4t.</li>\n"
        "</ul>\n"
        f"<p><em>Deine Anfrage:</em> <code>{_escape(request_line)}</code></p>\n"
        "<a class=\"btn\" href=\"/wiki\">Zur Hidden Wiki \u2192</a>\n"
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
            f"<li><a href=\"{url}\">{name}</a> \u2014 {desc}<br><code>{url}</code></li>"
        )
    if not items:
        items.append("<li><em>Noch keine Eintr\u00e4ge. Bearbeite wiki.json und mounte sie neu.</em></li>")
    body = (
        "<h1>Hidden Wiki</h1>\n"
        "<p>Eine Liste von Diensten im Erebos-Netzwerk. Platzhalter-Eintr\u00e4ge, bis echte Dienste existieren.</p>\n"
        f"<ul>\n{chr(10).join(items)}\n</ul>\n"
        "<a class=\"btn\" href=\"/\">\u2190 Zur\u00fcck zur Startseite</a>\n"
    )
    return _page("Hidden Wiki", address, body)
