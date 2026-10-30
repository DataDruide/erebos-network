import base64
from pathlib import Path

"""HTML-Renderer fuer Erebos Network.

Modernes "Deepweb/Hacking"-Theme:
- Glassmorphism (backdrop-filter)
- Neon-Glow (box-shadow + text-shadow)
- Gradient-Text (background-clip)
- Grid-Layout
- Hover-Animationen
- Terminal-Cursor
- Animated Background
- Custom Scrollbar
- Focus-Rings
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


def _load_bg_image(name: str) -> str:
    """Laedt ein Bild aus assets/ als Base64-Data-URI (oder "")."""
    try:
        p = Path(__file__).parent / "assets" / name
        if p.exists():
            data = base64.b64encode(p.read_bytes()).decode("ascii")
            ext = p.suffix.lower().lstrip(".")
            mime = {"jpeg": "image/jpeg", "jpg": "image/jpeg",
                    "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
            return f"data:{mime};base64,{data}"
    except Exception:
        pass
    return ""


def _page(title: str, address: str, body: str, hero_image: str = "", body_bg: str = "") -> bytes:
    """Rendert eine komplette HTML-Seite mit optionalem Hero-Header.

    hero_image: Dateiname in assets/ (z.B. "mail-bg.jpeg") oder ""
    body_bg: Optionaler Seitenhintergrund (z.B. "55.jpeg")
    """
    if hero_image and not hero_image.startswith("data:"):
        hero_image = _load_bg_image(hero_image)

    # Hero-Header bauen (nur wenn Bild da)
    if hero_image:
        hero_html = (
            '<div class="hero">\n'
            f'  <div class="hero-bg" style="background-image: url(\'{hero_image}\');"></div>\n'
            '  <div class="hero-overlay"></div>\n'
            f'  <h1 class="hero-title">{_escape(title)}</h1>\n'
            '</div>\n'
        )
    else:
        hero_html = f'<h1>{_escape(title)}</h1>\n'

    html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"de\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"  <title>{_escape(title)}</title>\n"
        "  <style>\n"
        "    * { box-sizing: border-box; }\n"
        "    html { font-size: 16px; scroll-behavior: smooth; }\n"
        "    body {\n"
        "      background: #050508;\n"
        "      color: #c8d8c8;\n"
        "      font-family: 'Courier New', 'Monaco', monospace;\n"
        "      font-size: 1rem;\n"
        "      max-width: 900px;\n"
        "      margin: 0 auto;\n"
        "      padding: 0;\n"
        "      line-height: 1.7;\n"
        "      min-height: 100vh;\n"
        "      position: relative;\n"
        "    }\n"
        "    body::before {\n"
        "      content: '';\n"
        "      position: fixed;\n"
        "      top: 0; left: 0; right: 0; bottom: 0;\n"
        "      background: repeating-linear-gradient(0deg,\n"
        "        rgba(0,255,136,0.03) 0px, rgba(0,255,136,0.03) 1px,\n"
        "        transparent 1px, transparent 3px);\n"
        "      pointer-events: none;\n"
        "      z-index: 9999;\n"
        "      animation: scanlineMove 8s linear infinite;\n"
        "    }\n"
        "    @keyframes scanlineMove {\n"
        "      0% { background-position: 0 0; }\n"
        "      100% { background-position: 0 100vh; }\n"
        "    }\n"
        "    /* === HERO HEADER === */\n"
        "    .hero {\n"
        "      position: relative;\n"
        "      width: 100%;\n"
        "      height: 320px;\n"
        "      overflow: hidden;\n"
        "      border-bottom: 2px solid #00ff88;\n"
        "      margin-bottom: 2em;\n"
        "      box-shadow: 0 4px 30px rgba(0,255,136,0.2);\n"
        "    }\n"
        "    .hero-bg {\n"
        "      position: absolute;\n"
        "      top: 0; left: 0; right: 0; bottom: 0;\n"
        "      background-size: cover;\n"
        "      background-position: center;\n"
        "      filter: blur(1px) brightness(0.6) saturate(1.4);\n"
        "      transform: scale(1.05);\n"
        "    }\n"
        "    .hero-overlay {\n"
        "      position: absolute;\n"
        "      top: 0; left: 0; right: 0; bottom: 0;\n"
        "      background: linear-gradient(180deg,\n"
        "        rgba(5,5,8,0.3) 0%,\n"
        "        rgba(5,5,8,0.7) 60%,\n"
        "        rgba(5,5,8,0.95) 100%);\n"
        "    }\n"
        "    .hero-title {\n"
        "      position: absolute;\n"
        "      bottom: 1.5em;\n"
        "      left: 1.5em;\n"
        "      right: 1.5em;\n"
        "      margin: 0;\n"
        "      background: linear-gradient(135deg, #00ff88 0%, #00ffcc 50%, #00ff88 100%);\n"
        "      -webkit-background-clip: text;\n"
        "      background-clip: text;\n"
        "      -webkit-text-fill-color: transparent;\n"
        "      color: #00ff88;\n"
        "      font-size: 2.4rem;\n"
        "      font-weight: 700;\n"
        "      letter-spacing: 0.2em;\n"
        "      text-shadow: 0 0 30px rgba(0,255,136,0.6), 0 4px 8px rgba(0,0,0,0.9);\n"
        "      word-break: break-word;\n"
        "    }\n"
        "    .content {\n"
        "      padding: 0 1.5em 2em 1.5em;\n"
        "    }\n"
        "    /* === INHALT === */\n"
        "    ::selection { background: #00ff88; color: #050508; }\n"
        "    ::-webkit-scrollbar { width: 10px; background: #0a0a15; }\n"
        "    ::-webkit-scrollbar-thumb { background: #00ff88; border-radius: 2px; }\n"
        "    h1 {\n"
        "      background: linear-gradient(135deg, #00ff88 0%, #00ffcc 50%, #00ff88 100%);\n"
        "      -webkit-background-clip: text;\n"
        "      background-clip: text;\n"
        "      -webkit-text-fill-color: transparent;\n"
        "      color: #00ff88;\n"
        "      font-size: 1.8rem;\n"
        "      font-weight: 700;\n"
        "      letter-spacing: 0.2em;\n"
        "      text-shadow: 0 0 30px rgba(0,255,136,0.6);\n"
        "      border-bottom: 1px solid rgba(0,255,136,0.4);\n"
        "      padding-bottom: 0.5em;\n"
        "      margin-bottom: 1.5em;\n"
        "      word-break: break-word;\n"
        "    }\n"
        "    h2 {\n"
        "      color: #00ff88;\n"
        "      font-size: 1.15rem;\n"
        "      letter-spacing: 0.15em;\n"
        "      margin-top: 2em;\n"
        "      margin-bottom: 0.8em;\n"
        "      text-shadow: 0 0 10px rgba(0,255,136,0.7);\n"
        "    }\n"
        "    h2::before { content: '> '; color: #00ff88; }\n"
        "    h3 {\n"
        "      color: #00ff88;\n"
        "      font-size: 1rem;\n"
        "      letter-spacing: 0.1em;\n"
        "      margin-top: 1.5em;\n"
        "      margin-bottom: 0.5em;\n"
        "    }\n"
        "    p { margin: 0.8em 0; }\n"
        "    strong { color: #e0f0e0; font-weight: 700; }\n"
        "    em { color: #a0b8a8; font-style: italic; }\n"
        "    small { color: #8aaa98; font-size: 0.85em; }\n"
        "    a {\n"
        "      color: #00ff88;\n"
        "      text-decoration: none;\n"
        "      border-bottom: 1px dotted #00ff88;\n"
        "      transition: all 0.2s ease;\n"
        "    }\n"
        "    a:hover {\n"
        "      color: #050508;\n"
        "      background: #00ff88;\n"
        "      box-shadow: 0 0 12px rgba(0,255,136,0.8);\n"
        "      padding: 0 0.2em;\n"
        "    }\n"
        "    code {\n"
        "      background: rgba(10,10,21,0.9);\n"
        "      color: #00ff88;\n"
        "      padding: 0.2em 0.4em;\n"
        "      border: 1px solid rgba(0,255,136,0.3);\n"
        "      border-radius: 2px;\n"
        "      font-family: 'Courier New', monospace;\n"
        "      font-size: 0.9em;\n"
        "      word-break: break-all;\n"
        "    }\n"
        "    ul, ol { padding-left: 1.5em; margin: 0.8em 0; }\n"
        "    li { margin: 0.4em 0; }\n"
        "    li::marker { color: #00ff88; }\n"
        "    blockquote {\n"
        "      border-left: 3px solid #00ff88;\n"
        "      padding: 0.8em 1em;\n"
        "      margin: 1em 0;\n"
        "      color: #a0b8a8;\n"
        "      font-style: italic;\n"
        "      background: rgba(0,255,136,0.05);\n"
        "      border-radius: 0 4px 4px 0;\n"
        "    }\n"
        "    hr { border: none; border-top: 1px solid rgba(0,255,136,0.3); margin: 2em 0; }\n"
        "    table { border-collapse: collapse; width: 100%; margin: 1em 0; }\n"
        "    th, td { border: 1px solid rgba(0,255,136,0.3); padding: 0.5em 0.8em; text-align: left; }\n"
        "    th { background: rgba(0,255,136,0.1); color: #00ff88; }\n"
        "    tr:hover { background: rgba(0,255,136,0.05); }\n"
        "    .btn {\n"
        "      display: inline-block;\n"
        "      margin: 0.5em 0.5em 0.5em 0;\n"
        "      padding: 0.7em 1.4em;\n"
        "      background: rgba(0,255,136,0.1);\n"
        "      color: #00ff88;\n"
        "      border: 2px solid #00ff88;\n"
        "      border-radius: 4px;\n"
        "      text-decoration: none;\n"
        "      letter-spacing: 0.1em;\n"
        "      font-family: inherit;\n"
        "      font-size: 1rem;\n"
        "      cursor: pointer;\n"
        "      transition: all 0.25s;\n"
        "    }\n"
        "    .btn:hover {\n"
        "      background: #00ff88;\n"
        "      color: #050508;\n"
        "      transform: translateY(-2px);\n"
        "      box-shadow: 0 4px 20px rgba(0,255,136,0.7);\n"
        "    }\n"
        "    .btn:disabled { opacity: 0.5; cursor: not-allowed; }\n"
        "    .card {\n"
        "      border: 1px solid rgba(0,255,136,0.3);\n"
        "      background: rgba(10,10,21,0.7);\n"
        "      backdrop-filter: blur(8px);\n"
        "      padding: 1.2em;\n"
        "      margin: 1em 0;\n"
        "      border-radius: 4px;\n"
        "      transition: all 0.3s;\n"
        "    }\n"
        "    .card:hover {\n"
        "      border-color: #00ff88;\n"
        "      box-shadow: 0 0 20px rgba(0,255,136,0.3);\n"
        "    }\n"
        "    .panel {\n"
        "      border: 2px solid #00ff88;\n"
        "      background: rgba(0,255,136,0.05);\n"
        "      backdrop-filter: blur(8px);\n"
        "      padding: 1.2em;\n"
        "      margin: 1em 0;\n"
        "      border-radius: 4px;\n"
        "      box-shadow: 0 0 20px rgba(0,255,136,0.2);\n"
        "    }\n"
        "    .terminal {\n"
        "      background: rgba(0,0,0,0.9);\n"
        "      border: 1px solid #00ff88;\n"
        "      padding: 1em;\n"
        "      font-family: 'Courier New', monospace;\n"
        "      color: #00ff88;\n"
        "      overflow-x: auto;\n"
        "      border-radius: 4px;\n"
        "    }\n"
        "    .terminal::before { content: '$ '; color: #00ff88; }\n"
        "    .terminal::after { content: '_'; animation: blink 1s step-end infinite; color: #00ff88; }\n"
        "    @keyframes blink { 50% { opacity: 0; } }\n"
        "    .addr {\n"
        "      margin-top: 3em;\n"
        "      padding: 1.5em;\n"
        "      border-top: 1px solid rgba(0,255,136,0.3);\n"
        "      font-size: 0.75rem;\n"
        "      color: #6a8a7a;\n"
        "      letter-spacing: 0.1em;\n"
        "      word-break: break-all;\n"
        "    }\n"
        "    label { color: #00ff88; font-size: 0.9em; display: block; margin-top: 0.8em; }\n"
        "    input, textarea, select {\n"
        "      background: rgba(10,10,21,0.9);\n"
        "      color: #e0f0e0;\n"
        "      border: 1px solid rgba(0,255,136,0.5);\n"
        "      padding: 0.7em;\n"
        "      font-family: 'Courier New', monospace;\n"
        "      font-size: 1rem;\n"
        "      border-radius: 4px;\n"
        "      width: 100%;\n"
        "      margin-top: 0.3em;\n"
        "      transition: all 0.2s;\n"
        "    }\n"
        "    input::placeholder, textarea::placeholder { color: #6a8a7a; }\n"
        "    input:focus, textarea:focus {\n"
        "      outline: none;\n"
        "      border-color: #00ff88;\n"
        "      box-shadow: 0 0 0 3px rgba(0,255,136,0.3);\n"
        "    }\n"
        "    /* Highlight fuer #last-post */\n"
        "    [id=\"last-post\"]:target {\n"
        "      background: rgba(0,255,136,0.1) !important;\n"
        "      border: 1px solid #00ff88 !important;\n"
        "      box-shadow: 0 0 20px rgba(0,255,136,0.5) !important;\n"
        "      animation: highlight 2s ease;\n"
        "    }\n"
        "    @keyframes highlight {\n"
        "      0% { background: rgba(0,255,136,0.4); }\n"
        "      100% { background: rgba(0,255,136,0.1); }\n"
        "    }\n"
        "    .warning { color: #ffaa33; }\n"
        "    .error { color: #ff4444; }\n"
        "    .success { color: #00ff88; }\n"
        "    @media (max-width: 600px) {\n"
        "      body { font-size: 0.95rem; }\n"
        "      .hero { height: 200px; }\n"
        "      .hero-title { font-size: 1.6rem; left: 1em; bottom: 1em; }\n"
        "      .content { padding: 0 1em 1.5em 1em; }\n"
        "    }\n"
        "    @media (prefers-reduced-motion: reduce) {\n"
        "      *, *::before, *::after { animation: none !important; transition: none !important; }\n"
        "    }\n"
        "    /* === ONBOARDING === */\n"
        "    .wrap { padding: 0 1.5em 3em; }\n"
        "    .hero { display: flex; justify-content: space-between; align-items: center;\n"
        "            padding: 1.5em 1.5em 0.5em; border-bottom: 1px solid rgba(0,255,136,0.4);\n"
        "            margin-bottom: 2em; height: auto; }\n"
        "    .brand { font-size: 0.9rem; letter-spacing: 0.2em; color: #00ff88;\n"
        "             display: flex; align-items: center; }\n"
        "    .badge { font-size: 0.7rem; padding: 0.3em 0.8em; border: 1px solid #00ff88;\n"
        "             color: #00ff88; border-radius: 4px; letter-spacing: 0.15em; }\n"
        "    .title { font-size: 2rem; letter-spacing: 0.2em; margin: 0 0 0.5em;\n"
        "             color: #00ff88; }\n"
        "    .subtitle { color: #889988; margin-bottom: 2em; font-size: 0.95rem; }\n"
        "    .card { background: rgba(0,255,136,0.03); border: 1px solid #1a2a1a;\n"
        "            border-radius: 8px; padding: 1.5em; margin-bottom: 1.5em; }\n"
        "    .card-label { font-size: 0.7rem; letter-spacing: 0.2em; color: #00ff88;\n"
        "                  margin-bottom: 1em; text-transform: uppercase; }\n"
        "    .uuid { display: block; width: 100%; background: #0a0a15; border: 1px solid #1a2a1a;\n"
        "            color: #00ff88; font-family: inherit; font-size: 1rem; padding: 0.8em;\n"
        "            border-radius: 4px; margin-bottom: 0.8em; }\n"
        "    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));\n"
        "            gap: 1em; margin-bottom: 1.5em; }\n"
        "    .tile { display: block; background: rgba(0,255,136,0.02); border: 1px solid #1a2a1a;\n"
        "            border-radius: 6px; padding: 1em 1.2em; text-decoration: none; color: #c8d8c8; }\n"
        "    .tile:hover { border-color: rgba(0,255,136,0.4); }\n"
        "    .tile-title { font-size: 0.85rem; letter-spacing: 0.15em; color: #00ff88; }\n"
        "    .tile-sub { font-size: 0.8rem; color: #667766; }\n"
        "    .kv { width: 100%; border-collapse: collapse; }\n"
        "    .kv td { padding: 0.5em 0; border-bottom: 1px solid #1a2a1a; }\n"
        "    .kv td:first-child { color: #667766; width: 40%; }\n"
        "    .ok { color: #00ff88; }\n"
        "    .dim { color: #556655; }\n"
        "    .rights { list-style: none; padding: 0; margin: 0; }\n"
        "    .rights li { padding: 0.5em 0 0.5em 1.5em; }\n"
        "    .btn { display: inline-block; padding: 0.6em 1.2em; border: 1px solid #00ff88;\n"
        "           color: #00ff88; text-decoration: none; border-radius: 4px; }\n"
        "    .foot { margin-top: 3em; padding-top: 2em; border-top: 1px solid #1a2a1a; }\n"
        "    .foot-nav { display: flex; gap: 1.5em; flex-wrap: wrap; }\n"
        "    .foot-nav a { color: #889988; text-decoration: none; }\n"
        "  </style>\n"
        "</head>\n"

        "<body>\n"
        + hero_html +
        '<div class="content">\n'
        f"{body}\n"
        f'<p class="addr"><strong>Diese Instanz:</strong> <code>{_escape(address)}</code></p>\n'
        "</div>\n"
        "</body>\n"
        "</html>\n"
    )
    # body_bg: Platzhalter ersetzen + Div einfügen
    if body_bg:
        _bg_url = _load_bg_image(body_bg)
        if _bg_url:
            html = html.replace("{{BODY_BG}}", _bg_url)
        else:
            html = html.replace("{{BODY_BG}}", "")
    else:
        html = html.replace("{{BODY_BG}}", "")

    return html.encode("utf-8")


def _render_identity_box(anon_uuid: str) -> str:
    """Rendert eine Box mit UUID, @erebos-Adresse und Forum-Username."""
    from .forum_db import get_identity
    ident = get_identity(anon_uuid)
    email = ident["email"] if ident else anon_uuid.replace("-", "")[:8] + "@erebos"
    forum_username = (ident["forum_username"] if ident else None) or "(wird beim ersten Forum-Login angelegt)"

    return (
        '<div class="panel" style="margin:1em 0;">'
        '<p style="color:#00ff88; font-size:0.85em; letter-spacing:0.15em; '
        'margin-bottom:0.8em;">DEINE IDENTITAET</p>'
        '<p style="margin:0.4em 0;"><strong>UUID:</strong> '
        '<code style="word-break:break-all;">' + _escape(anon_uuid) + '</code></p>'
        '<p style="margin:0.4em 0;"><strong>E-Mail:</strong> '
        '<code>' + _escape(email) + '</code></p>'
        '<p style="margin:0.4em 0;"><strong>Forum:</strong> '
        '<code>' + _escape(forum_username) + '</code></p>'
        '</div>'
    )
