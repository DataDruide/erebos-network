"""HTML-Renderer fuer Erebos Network.

Enthaelt die Basis-Funktionen, die von allen Seiten genutzt werden:
- _page(): HTML-Grundgeruest
- _escape(): HTML-Escaping
- _format_timestamp(): Unix-Timestamp -> lesbares Datum
- _render_identity_box(): Identitaets-Box (UUID + @erebos + Forum)
"""


def _format_timestamp(ts: float) -> str:
    """Formatiert einen Unix-Timestamp als lesbares Datum."""
    import time as _time
    try:
        return _time.strftime("%Y-%m-%d %H:%M", _time.localtime(ts))
    except Exception:
        return "?"


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


def _render_identity_box(anon_uuid: str) -> str:
    """Rendert eine Box mit UUID, @erebos-Adresse und Forum-Username."""
    from .forum_db import get_identity
    ident = get_identity(anon_uuid)
    email = ident["email"] if ident else anon_uuid.replace("-", "")[:8] + "@erebos"
    forum_username = (ident["forum_username"] if ident else None) or "(wird beim ersten Forum-Login angelegt)"

    return (
        '<div style="border:2px solid #00ff88; padding:1em; margin:1em 0; '
        'background:#0a0a15; border-radius:4px;">'
        '<p style="color:#00ff88; font-size:0.85em; letter-spacing:0.15em; '
        'margin-bottom:0.8em;">DEINE IDENTITAET</p>'
        '<p style="margin:0.4em 0;"><strong>UUID:</strong> '
        '<code style="color:#00ff88; word-break:break-all;">' + _escape(anon_uuid) + '</code></p>'
        '<p style="margin:0.4em 0;"><strong>E-Mail:</strong> '
        '<code style="color:#00ff88;">' + _escape(email) + '</code></p>'
        '<p style="margin:0.4em 0;"><strong>Forum:</strong> '
        '<code style="color:#00ff88;">' + _escape(forum_username) + '</code></p>'
        '</div>'
    )
