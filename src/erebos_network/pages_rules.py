"""Rendert die Regeln des Erebos-Netzwerks."""

def render_rules(address: str) -> bytes:
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Regeln - Erebos</title>
  <style>
    body {{ background: #0d1117; color: #c9d1d9; font-family: sans-serif; padding: 2em; }}
    h1 {{ color: #00ff41; font-family: monospace; }}
    .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 1.5em; margin-bottom: 2em; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ margin-bottom: 1em; }}
    strong {{ color: #00ff41; }}
    a {{ color: #39ff14; text-decoration: none; }}
  </style>
</head>
<body>
  <h1>Regeln des Erebos-Netzwerks</h1>
  <div class="card">
    <ul>
      <li><strong>1. Anonymität wahren:</strong> Teile niemals persönliche Daten oder deine echte Identität.</li>
      <li><strong>2. Respektvoller Umgang:</strong> Keine Beleidigungen, Hassrede oder Mobbing.</li>
      <li><strong>3. Keine illegalen Inhalte:</strong> Das Netzwerk darf nicht für Straftaten genutzt werden.</li>
      <li><strong>4. Spam vermeiden:</strong> Keine unnötigen Wiederholungen oder Werbung.</li>
      <li><strong>5. Sicherheit:</strong> Melde Sicherheitslücken vertraulich an die Administratoren.</li>
    </ul>
  </div>
  <p><a href="/">&larr; Zurück zur Startseite</a></p>
  <p style="color:#30363d; font-size:0.8em; margin-top:3em;">Diese Instanz: {address}</p>
</body>
</html>"""
    return html.encode("utf-8")
