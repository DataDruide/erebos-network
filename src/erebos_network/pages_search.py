"""Rendert die Suchmaschinen-Seite (modern, mit Hintergrundbild)."""

import base64
from pathlib import Path as _Path


def _get_bg_url() -> str:
    """Gibt die URL zum Hintergrundbild zurück (via /static/-Endpoint)."""
    return "/static/desktop3.jpeg"


def render_search(address: str, query: str) -> bytes:
    """Baut das HTML für die Suchseite (XSS-sicher, modern)."""
    import html as _html
    from .search_engine import search_all

    query_safe = _html.escape(query, quote=True)
    results = search_all(query) if query else []
    bg_url = _get_bg_url()

    # Ergebnis-Karten
    results_html = ""
    if query:
        if not results:
            results_html = (
                '<div class="empty-state">'
                '<div class="icon">🔍</div>'
                '<p>Keine Ergebnisse fuer "<strong>' + query_safe + '</strong>".</p>'
                '<p style="font-size:.8rem;margin-top:.5rem;">Versuch es mit einem anderen Begriff.</p>'
                '</div>'
            )
        else:
            for r in results:
                results_html += (
                    '<div class="result-card">'
                    f'<span class="result-type">{_html.escape(r["type"])}</span>'
                    f'<a class="result-title" href="{_html.escape(r["url"])}">{_html.escape(r["title"])}</a>'
                    f'<p class="result-snippet">{_html.escape(r["snippet"])}</p>'
                    f'<div class="result-footer"><span class="result-url">{_html.escape(r["url"])}</span>'
                    f'<button class="copy-btn" data-copy="{_html.escape(r["url"])}">Kopieren</button></div>'
                    '</div>'
                )
    else:
        results_html = (
            '<div class="empty-state">'
            '<div class="icon">🔍</div>'
            '<p>Gib einen Suchbegriff ein.</p>'
            '<p style="font-size:.8rem;margin-top:.5rem;">Durchsuche Threads, Wiki-Eintraege, Mails und mehr.</p>'
            '</div>'
        )


    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Erebos Search</title>
<style>
  :root {{
    --bg: #050508;
    --bg-card: #0d1117;
    --bg-card-hover: #161b22;
    --fg: #e6edf3;
    --fg-dim: #7d8590;
    --accent: #ff3333;
    --accent-dim: rgba(255, 51, 51, 0.15);
    --warn: #fbbf24;
    --danger: #da3633;
    --border: #30363d;
    --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    background: var(--bg);
    color: var(--fg);
    font-family: var(--font);
    font-size: 15px;
    line-height: 1.6;
    min-height: 100vh;
    padding: 2rem 1rem;
    background-image:
      linear-gradient(rgba(5, 5, 8, 0.92), rgba(5, 5, 8, 0.98)),
      url('/static/hacker.jpeg');
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    background-repeat: no-repeat;
  }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  header {{ text-align: center; margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--border); }}
  h1 {{ font-size: 2rem; color: var(--accent); letter-spacing: 2px; text-transform: uppercase; margin-bottom: .5rem; text-shadow: 0 0 20px rgba(255, 51, 51, 0.3); }}
  .subtitle {{ color: var(--fg-dim); font-size: .85rem; }}
  .privacy-banner {{ background: rgba(255, 51, 51, 0.08); border-left: 4px solid var(--accent); padding: 12px 16px; border-radius: 4px; margin-bottom: 1.5rem; font-size: 0.85em; color: #ffcccc; display: flex; align-items: center; gap: 10px; }}
  .privacy-banner .icon {{ font-size: 1.2em; }}
  .hero-search {{ margin: 2rem auto 3rem; max-width: 700px; position: relative; }}
  .hero-search input {{
    width: 100%; background: var(--bg-card); border: 2px solid var(--border);
    color: var(--fg); padding: 1rem 1rem 1rem 3rem;
    font-family: var(--font); font-size: 1.1rem; border-radius: 10px;
    transition: border-color .3s ease;
  }}
  .hero-search input:focus {{
    outline: none; border-color: var(--accent);
  }}
  .hero-search::before {{
    content: '\2315'; position: absolute; left: 1.2rem; top: 50%;
    transform: translateY(-50%); color: var(--accent); font-size: 1.5rem;
    pointer-events: none;
  }}
  .hero-search button {{
    position: absolute; right: .4rem; top: 50%; transform: translateY(-50%);
    background: var(--danger); color: #fff; border: none;
    padding: .6rem 1.2rem; font-family: var(--font); font-size: .9rem;
    font-weight: 600; border-radius: 6px; cursor: pointer; transition: background-color .3s ease;
  }}
  .hero-search button:hover {{ background: var(--accent); }}
  .results {{ max-width: 800px; margin: 0 auto; }}
  .result-card {{
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 8px; padding: 1.5em; margin-bottom: 1rem;
    transition: border-color .3s ease, background-color .3s ease;
  }}
  .result-card:hover {{ border-color: var(--accent); background: var(--bg-card-hover); }}
  .result-type {{
    display: inline-block; background: var(--accent-dim); color: var(--accent);
    padding: .1rem .5rem; border-radius: 4px; font-size: .7rem;
    text-transform: uppercase; letter-spacing: 1px; margin-bottom: .5rem;
  }}
  .result-title {{
    color: var(--accent); font-size: 1.2rem; font-weight: bold;
    text-decoration: none; display: block; margin-bottom: .5rem;
  }}
  .result-title:hover {{ text-decoration: underline; }}
  .result-snippet {{ color: var(--fg-dim); font-size: .85rem; margin-bottom: .8rem; }}
  .result-footer {{ display: flex; justify-content: space-between; align-items: center; font-size: .75rem; }}
  .result-url {{ color: var(--fg-dim); word-break: break-all; max-width: 80%; }}
  .copy-btn {{
    background: var(--accent-dim); border: 1px solid var(--accent); color: var(--accent);
    padding: .2rem .6rem; border-radius: 4px; cursor: pointer;
    font-size: .7rem; font-family: var(--font); transition: background-color .3s, color .3s;
  }}
  .copy-btn:hover {{ background: var(--accent); color: #fff; }}
  .empty-state {{ text-align: center; padding: 3rem 1rem; color: var(--fg-dim); }}
  .empty-state .icon {{ font-size: 3rem; margin-bottom: 1rem; opacity: .5; }}
  .footer {{
    text-align: center; padding-top: 2rem; margin-top: 2rem;
    border-top: 1px solid var(--border); color: var(--fg-dim); font-size: .8rem;
  }}
  .footer a {{ color: var(--accent); text-decoration: none; border-bottom: 1px dashed var(--accent); }}
  .footer a:hover {{ border-bottom-style: solid; }}
  .instance {{ margin-top: .5rem; font-size: .75rem; word-break: break-all; }}
  .toast {{
    position: fixed; bottom: 2rem; left: 50%;
    transform: translateX(-50%) translateY(100px);
    background: var(--accent); color: #fff; padding: .7rem 1.4rem;
    border-radius: 6px; font-weight: bold; font-size: .85rem;
    opacity: 0; transition: transform .3s, opacity .3s;
    pointer-events: none; z-index: 1000;
  }}
  .toast.show {{ transform: translateX(-50%) translateY(0); opacity: 1; }}
  ::-webkit-scrollbar {{ width: 8px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}
  ::-webkit-scrollbar-thumb:hover {{ background: var(--accent); }}
</style>
</head>
<body>
<div class="bg"></div>
<div class="container">
  <header>
    <h1>Erebos Search</h1>
    <p class="subtitle">Durchsuche das gesamte Erebos-Netzwerk</p>
  </header>

  <form method="GET" action="/search" class="hero-search">
    <input type="text" name="q" value="{query_safe}" placeholder="Suche nach Threads, Wiki-Eintraegen, Mails..." autofocus autocomplete="off">
    <button type="submit">Suchen</button>
  </form>

  <div class="results">
    {results_html}
  </div>

  <footer class="footer">
    <a href="/">← Zurueck zur Startseite</a>
    <div class="instance">Diese Instanz: {address}</div>
  </footer>
</div>

<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>
(() => {{
  'use strict';
  const toast = document.getElementById('toast');
  let toastTimer;
  function showToast(msg) {{
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 2500);
  }}
  document.querySelectorAll('.copy-btn').forEach(btn => {{
    btn.addEventListener('click', async (e) => {{
      e.preventDefault();
      e.stopPropagation();
      try {{
        await navigator.clipboard.writeText(btn.dataset.copy);
        showToast('Kopiert!');
      }} catch {{
        showToast('Kopieren fehlgeschlagen');
      }}
    }});
  }});
}})();
</script>
</body>
</html>"""
    return html.encode("utf-8")
