"""HTML-Renderer für den Service-Bereich (/service)."""

from .renderers import _page, _escape


def render_services_list(address: str, services: list[dict]) -> bytes:
    """Zeigt alle Services als Tabelle + 'Neuen Service erstellen'-Formular."""
    rows = ""
    for s in services:
        rows += f"""
        <tr>
          <td>{_escape(s['name'])}</td>
          <td>{s['port']}</td>
          <td><span class="{'ok' if s['status'] == 'läuft' else 'dim'}">● {s['status']}</span></td>
          <td><code>{_escape(s['address'])}</code></td>
          <td>
            <form method="POST" action="/service/{_escape(s['name'])}/stop" style="display:inline;">
              <button type="submit" class="btn-small">Stop</button>
            </form>
            <form method="POST" action="/service/{_escape(s['name'])}/delete" style="display:inline;">
              <button type="submit" class="btn-small" onclick="return confirm('Service löschen?')">Löschen</button>
            </form>
          </td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="5" class="dim">Keine Services. Erstelle deinen ersten!</td></tr>'

    body = f"""
<div class="wrap">
  <header class="hero">
    <div class="brand"><span class="dot"></span> EREBOS NETWORK</div>
    <div class="badge">SERVICES</div>
  </header>
  <h1 class="title">EIGENE SERVICES</h1>
  <p class="subtitle">Starte deinen eigenen Hidden Service mit eigener .erebos-Adresse.</p>

  <section class="card">
    <div class="card-label">DEINE SERVICES</div>
    <table class="kv" style="width:100%;">
      <thead>
        <tr><th>Name</th><th>Port</th><th>Status</th><th>Adresse</th><th>Aktion</th></tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </section>

  <section class="card">
    <div class="card-label">NEUEN SERVICE ERSTELLEN</div>
    <form method="POST" action="/service/create">
      <div style="margin-bottom:1em;">
        <label>Name</label><br>
        <input class="uuid" name="name" placeholder="z.B. mein-wiki" required>
      </div>
      <div style="margin-bottom:1em;">
        <label>Port (8083–8099)</label><br>
        <input class="uuid" name="port" type="number" min="8083" max="8099" value="8083" required>
      </div>
      <div style="margin-bottom:1em;">
        <label>HTML-Verzeichnis (absoluter Pfad)</label><br>
        <input class="uuid" name="pages" placeholder="/Users/du/mein_wiki" required>
      </div>
      <button type="submit" class="btn">Service erstellen</button>
    </form>
  </section>

  <footer class="foot">
    <nav class="foot-nav">
      <a href="/">Startseite</a>
      <a href="/forum">Forum</a>
      <a href="/wiki">Hidden Wiki</a>
    </nav>
  </footer>
</div>
"""
    return _page("SERVICES", address, body, hero_image="")


def render_service_error(address: str, message: str) -> bytes:
    """Fehlerseite für Service-Aktionen."""
    body = f"""
<div class="wrap">
  <header class="hero">
    <div class="brand"><span class="dot"></span> EREBOS NETWORK</div>
    <div class="badge">FEHLER</div>
  </header>
  <h1 class="title">FEHLER</h1>
  <section class="card">
    <p>{_escape(message)}</p>
    <a class="btn" href="/service">Zurück zu den Services</a>
  </section>
</div>
"""
    return _page("FEHLER", address, body, hero_image="")

def render_upload_form(address: str, name: str, files: list[str]) -> bytes:
    """HTML-Formular für Datei-Upload."""
    file_rows = "".join(
        f'<li><code>{_escape(f)}</code></li>' for f in files
    ) or '<li class="dim">(keine Dateien)</li>'

    body = f"""
<div class="wrap">
  <header class="hero">
    <div class="brand"><span class="dot"></span> EREBOS NETWORK</div>
    <div class="badge">UPLOAD</div>
  </header>
  <h1 class="title">DATEIEN HOCHLADEN</h1>
  <p class="subtitle">Service: <strong>{_escape(name)}</strong></p>

  <section class="card">
    <div class="card-label">AKTUELLE DATEIEN</div>
    <ul class="rights">{file_rows}</ul>
  </section>

  <section class="card">
    <div class="card-label">NEUE DATEI HOCHLADEN</div>
    <form method="POST" action="/service/{_escape(name)}/upload" enctype="multipart/form-data">
      <div style="margin-bottom:1em;">
        <label>Datei (HTML, CSS, JS, JSON, Bilder)</label><br>
        <input type="file" name="file" accept=".html,.htm,.css,.js,.json,.svg,.png,.jpg,.txt" required>
      </div>
      <button type="submit" class="btn">Hochladen</button>
    </form>
  </section>

  <footer class="foot">
    <nav class="foot-nav">
      <a href="/service">Zurück zu den Services</a>
    </nav>
  </footer>
</div>
"""
    return _page("UPLOAD", address, body, hero_image="")

