"""Onboarding-Flow: Progressbar-Seite + Welcome-Seite."""

import logging

logger = logging.getLogger(__name__)


ONBOARD_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>EREBOS - Verbinde</title>
  <meta http-equiv="refresh" content="3;url=/welcome">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #050508;
      color: #00ff88;
      font-family: 'Courier New', 'Monaco', monospace;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }
    .scanlines {
      position: fixed; top: 0; left: 0; right: 0; bottom: 0;
      background: repeating-linear-gradient(
        0deg,
        rgba(0, 255, 136, 0.03) 0px,
        rgba(0, 255, 136, 0.03) 1px,
        transparent 1px,
        transparent 3px
      );
      pointer-events: none;
      z-index: 10;
    }
    .container {
      max-width: 640px;
      padding: 3em 2em;
      position: relative;
      z-index: 5;
    }
    h1 {
      font-size: 1.4em;
      letter-spacing: 0.3em;
      color: #00ff88;
      margin-bottom: 3em;
      text-align: center;
      text-shadow: 0 0 15px rgba(0, 255, 136, 0.6);
    }
    .steps { list-style: none; }
    .step {
      padding: 0.8em 0;
      color: #004433;
      font-size: 0.95em;
      opacity: 0.4;
      position: relative;
      animation: activate 2.5s ease forwards;
    }
    .step::before {
      content: "[ ]";
      margin-right: 1em;
      color: #004433;
      font-weight: bold;
      animation: check 2.5s ease forwards;
    }
    .step:nth-child(1) { animation-delay: 0.0s; }
    .step:nth-child(2) { animation-delay: 0.5s; }
    .step:nth-child(3) { animation-delay: 1.0s; }
    .step:nth-child(4) { animation-delay: 1.5s; }
    .step:nth-child(5) { animation-delay: 2.0s; }
    .step:nth-child(1)::before { animation-delay: 0.0s; }
    .step:nth-child(2)::before { animation-delay: 0.5s; }
    .step:nth-child(3)::before { animation-delay: 1.0s; }
    .step:nth-child(4)::before { animation-delay: 1.5s; }
    .step:nth-child(5)::before { animation-delay: 2.0s; }
    @keyframes activate {
      0% { opacity: 0.4; color: #004433; }
      15% { opacity: 1; color: #00ff88; text-shadow: 0 0 8px rgba(0,255,136,0.5); }
      100% { opacity: 1; color: #008855; }
    }
    @keyframes check {
      0% { content: "[ ]"; color: #004433; }
      15% { content: "[>]"; color: #00ff88; }
      100% { content: "[*]"; color: #00ff88; }
    }
    .progress-bar {
      height: 4px;
      background: #0a0a15;
      margin: 3em 0 1em 0;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      width: 0;
      background: #00ff88;
      box-shadow: 0 0 12px #00ff88, 0 0 24px rgba(0, 255, 136, 0.5);
      animation: fill 2.5s ease forwards;
    }
    @keyframes fill {
      0% { width: 0; }
      100% { width: 100%; }
    }
    .status-text {
      text-align: center;
      color: #00ff88;
      font-size: 0.85em;
      letter-spacing: 0.2em;
      margin-top: 1em;
      min-height: 1.2em;
      animation: status 2.5s ease forwards;
    }
    .status-text::after {
      content: "INITIALISIERE...";
    }
    @keyframes status {
      0% { content: "INITIALISIERE..."; }
      20% { content: "TUNNEL ZUM RENDEZVOUS..."; }
      40% { content: "IDENTITAET ERZEUGEN..."; }
      60% { content: "SCHLUESSEL GENERIEREN..."; }
      80% { content: "POSTFACH EINRICHTEN..."; }
      100% { content: "BEREIT."; }
    }
    .footer {
      margin-top: 4em;
      text-align: center;
      font-size: 0.7em;
      color: #003322;
      letter-spacing: 0.1em;
      word-break: break-all;
    }
  </style>
</head>
<body>
<div class="scanlines"></div>
<div class="container">
  <h1>EREBOS NETWORK</h1>
  <ul class="steps">
    <li class="step" data-step="1">Tunnel zum Rendezvous-Punkt</li>
    <li class="step" data-step="2">Identitaet erzeugen</li>
    <li class="step" data-step="3">Kryptographische Schluessel</li>
    <li class="step" data-step="4">Postfach einrichten</li>
    <li class="step" data-step="5">Bereit</li>
  </ul>
  <div class="progress-bar"><div class="progress-fill"></div></div>
  <p class="status-text"></p>
  <p class="footer">{address}</p>
</div>
</body>
</html>
"""


def render_onboard(anon_uuid, address, _page, _escape):
    """Progressbar-Seite. Ruft create_identity auf (idempotent)."""
    from .forum_db import create_identity
    try:
        create_identity(anon_uuid)
    except Exception as e:
        logger.error(f"create_identity fehlgeschlagen: {e}")
    html = ONBOARD_HTML.replace("{address}", _escape(address))
    return html.encode("utf-8")


def render_welcome_onboarded(anon_uuid, address, _page, _escape):
    """Willkommens-Seite: UUID, E-Mail, Forum-Username, Warnung."""
    from .forum_db import get_identity, create_identity
    ident = get_identity(anon_uuid)
    if ident is None:
        try:
            create_identity(anon_uuid)
            ident = get_identity(anon_uuid)
        except Exception as e:
            logger.error(f"create_identity fehlgeschlagen: {e}")
            ident = None
    if ident is None:
        return _page(
            "Willkommen", address,
            "<h1>Fehler</h1><p>Identitaet konnte nicht erstellt werden.</p>",
        )

    email = ident["email"]
    forum_username = ident["forum_username"] or "(wird beim ersten Login angelegt)"

    # HTML mit einfachen Quotes (keine escaped quotes noetig)
    body = (
        '<h1>WILLKOMMEN BEI EREBOS</h1>'
        '<div style="border:2px solid #00ff88; padding:1.5em; margin:1.5em 0; background:#0a0a15;">'
        '<p style="color:#00ff88; font-size:0.9em; letter-spacing:0.15em; margin-bottom:1em;">DEINE IDENTITAET</p>'
        '<p style="margin:0.8em 0;"><strong>UUID:</strong><br>'
        '<code style="color:#00ff88; word-break:break-all;">' + _escape(anon_uuid) + '</code></p>'
        '<p style="margin:0.8em 0;"><strong>E-Mail:</strong><br>'
        '<code style="color:#00ff88;">' + _escape(email) + '</code></p>'
        '<p style="margin:0.8em 0;"><strong>Forum:</strong><br>'
        '<code style="color:#00ff88;">' + _escape(forum_username) + '</code></p>'
        '</div>'
        '<div style="border:2px solid #ff8800; padding:1.5em; margin:1.5em 0; background:#1a0f05;">'
        '<p style="color:#ff8800; font-size:1em; letter-spacing:0.1em; margin-bottom:0.8em;">WICHTIG - SCHREIB DAS AUF</p>'
        '<p style="color:#ffcc88; margin:0.5em 0; line-height:1.6;">'
        'Diese Daten werden <strong>nicht dauerhaft</strong> gespeichert. '
        'Nach einem Browser-Neustart sind sie <strong>verloren</strong>. '
        'Notiere UUID und E-Mail-Adresse jetzt.'
        '</p>'
        '</div>'
        '<form method="POST" action="/welcome/ack" style="margin:2em 0;">'
        '<button type="submit" class="btn" style="background:#00ff88; color:#000; font-weight:bold; padding:1em 2em;">'
        'Ich habe es aufgeschrieben'
        '</button>'
        '</form>'
        '<p style="text-align:center; margin-top:1em;">'
        '<a class="btn" href="/mail">-> Zum Postfach</a> '
        '<a class="btn" href="/forum">-> Zum Forum</a>'
        '</p>'
    )
    return _page("Willkommen", address, body)


def render_recover(address, _page, _escape, error=""):
    """Recovery-Seite: Formular fuer UUID/E-Mail-Eingabe.

    Args:
        error: Wenn gesetzt, wird eine Fehlermeldung angezeigt.
    """
    error_html = ""
    if error:
        error_html = (
            '<div style="border:2px solid #ff3333; padding:1em; '
            'margin:1em 0; background:#1a0505;">'
            '<p style="color:#ff6666;">' + _escape(error) + '</p>'
            '</div>'
        )

    body = (
        '<h1>IDENTITAET WIEDERHERSTELLEN</h1>'
        '<p>Gib deine UUID oder E-Mail-Adresse ein, um deine Identitaet '
        'zurueckzuholen.</p>'
        + error_html +
        '<form method="POST" action="/recover">'
        '<p><label>UUID oder E-Mail:<br>'
        '<input name="identifier" required '
        'style="width:100%; padding:0.8em; background:#0a0a15; '
        'color:#00ff88; border:2px solid #00ff88; font-family:monospace;" '
        'placeholder="z.B. a1b2c3d4-e5f6-... oder a1b2c3d4@erebos"></label></p>'
        '<p><button type="submit" class="btn" '
        'style="background:#00ff88; color:#000; font-weight:bold; '
        'padding:1em 2em; cursor:pointer; border:none;">'
        'Wiederherstellen</button></p>'
        '</form>'
        '<p style="margin-top:2em;"><a href="/">← Zurueck zur Startseite</a></p>'
    )
    return _page("Identitaet wiederherstellen", address, body)
