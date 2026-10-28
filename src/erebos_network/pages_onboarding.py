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


from .paths import app_file
WIKI_PATH = app_file("wiki.json")


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
    """Anonyme Begruessungsseite: duester, modern, dynamisch."""
    import uuid as _uuid
    import html as _html

    if client_id:
        anon_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))
    else:
        anon_uuid = str(_uuid.uuid4())

    short_id = anon_uuid[:8]
    e = lambda s: _html.escape(str(s), quote=True)

    body = f"""
<div class="wrap">
  <header class="hero">
    <div class="brand"><span class="dot"></span> EREBOS NETWORK</div>
    <div class="badge">● VERBUNDEN</div>
  </header>
  <h1 class="title">DU BIST VERBUNDEN</h1>
  <p class="subtitle">Diese Seite zeigt dir alles auf einen Blick. Kein Login. Kein Passwort. Keine Spur.</p>

  <section class="card">
    <div class="card-label">DEINE ANONYME KENNUNG</div>
    <input class="uuid" readonly value="{e(anon_uuid)}" onclick="this.select()">
    <div class="uuid-meta">Kurz-ID: <strong>#{e(short_id)}</strong> · gültig nur für diese Verbindung · nicht rückführbar auf IP oder Person</div>
  </section>

  <section class="grid">
    <a class="tile" href="/mail">
      <div class="tile-title">MAIL</div>
      <div class="tile-sub">anonym, UUID-basiert</div>
    </a>
    <a class="tile" href="/wiki">
      <div class="tile-title">HIDDEN WIKI</div>
      <div class="tile-sub">Verzeichnis der Dienste</div>
    </a>
    <a class="tile" href="/forum">
      <div class="tile-title">FORUM</div>
      <div class="tile-sub">Threads und Antworten</div>
    </a>
    <a class="tile" href="/regeln">
      <div class="tile-title">REGELN</div>
      <div class="tile-sub">was hier gilt</div>
    </a>
  </section>

  <section class="card">
    <div class="card-label">VERBINDUNG</div>
    <table class="kv">
      <tr><td>Status</td><td><span class="ok">● Verbunden</span></td></tr>
      <tr><td>Verschlüsselung</td><td>X25519 + ML-KEM-1024 + ChaCha20-Poly1305</td></tr>
      <tr><td>Routing</td><td>3-Hop-Onion (Proxy → peer2 → peer3 → peer1)</td></tr>
      <tr><td>Deine IP</td><td>für den Hidden Service <strong>unsichtbar</strong></td></tr>
      <tr><td>Anfrage</td><td><code>{e(request_line)}</code></td></tr>
    </table>
  </section>

  <section class="card">
    <div class="card-label">DEINE RECHTE</div>
    <ul class="rights">
      <li>Kein Login, kein Passwort, keine E-Mail-Adresse nötig.</li>
      <li>Keine personenbezogenen Daten werden gespeichert.</li>
      <li>Deine IP ist für den Hidden Service nicht sichtbar.</li>
      <li>Der Inhalt deiner Anfragen ist Ende-zu-Ende verschlüsselt.</li>
    </ul>
  </section>

  <details class="card">
    <summary><span class="card-label">SCHON EINE IDENTITÄT?</span> <span class="recover-hint">Identität wiederherstellen</span></summary>
    <p class="dim">Gib deine UUID oder E-Mail ein, um deine Identität wiederherzustellen. Dies ist keine Anmeldung — nur ein Wiederfinden deiner anonymen Kennung.</p>
    <a class="btn" href="/recover">Identität wiederherstellen →</a>
  </details>

  <footer class="foot">
    <div class="addr">
      <span class="dim">DIESE INSTANZ</span><br>
      <code>{e(address)}</code>
    </div>
    <nav class="foot-nav">
      <a href="/wiki">Hidden Wiki</a>
      <a href="/forum">Forum</a>
      <a href="/regeln">Regeln</a>
      <a href="/forum/health">Health</a>
    </nav>
  </footer>
</div>
"""
    return _page("WILLKOMMEN", address, body, hero_image="")
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
    return _page("WILLKOMMEN", address, body, hero_image="client-bg.jpeg")


def render_wiki(address: str) -> bytes:
    """Rendert das Hidden Wiki mit echten Erebos-Diensten."""
    html = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Hidden Wiki - Erebos</title>
  <style>
    body { background: #0d1117; color: #c9d1d9; font-family: sans-serif; padding: 2em; }
    h1 { color: #00ff41; font-family: monospace; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 1.5em; margin-bottom: 2em; }
    ul { list-style: none; padding: 0; }
    li { border-bottom: 1px solid #30363d; padding-bottom: 1em; margin-bottom: 1em; }
    a { color: #39ff14; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <h1>Hidden Wiki</h1>
  <p style="color: #8b949e;">Eine Liste der verfuegbaren Dienste im Erebos-Netzwerk.</p>
  <div class="card">
    <ul>
      <li><strong style="color:#00ff41;">Erebos Forum</strong><br><span style="color:#8b949e; font-size:0.9em;">Threads erstellen und diskutieren.</span><br><a href="/forum">/forum</a></li>
      <li><strong style="color:#00ff41;">Anonymes Postfach</strong><br><span style="color:#8b949e; font-size:0.9em;">Sichere Nachrichten empfangen und senden.</span><br><a href="/mail">/mail</a></li>
      <li><strong style="color:#00ff41;">Erebos Chat</strong><br><span style="color:#8b949e; font-size:0.9em;">Echtzeit-Kommunikation im Darknet.</span><br><a href="/chat">/chat</a></li>
      <li><strong style="color:#00ff41;">Regeln &amp; Richtlinien</strong><br><span style="color:#8b949e; font-size:0.9em;">Die Regeln des Erebos-Netzwerks.</span><br><a href="/rules">/rules</a></li>
    </ul>
  </div>
  <p><a href="/">&larr; Zurueck zur Startseite</a></p>
  <p style="color:#30363d; font-size:0.8em; margin-top:3em;">Diese Instanz: """ + address + """</p>
</body>
</html>"""
    return html.encode("utf-8")
