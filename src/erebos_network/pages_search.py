"""Rendert die Suchmaschinen-Seite."""

def render_search(address: str, query: str) -> bytes:
    """Baut das HTML für die Suchseite."""
    from .search_engine import search_all
    
    results = search_all(query) if query else []
    
    results_html = ""
    if query:
        if not results:
            results_html = "<p style='color:#8b949e;'>Keine Ergebnisse gefunden.</p>"
        else:
            for r in results:
                results_html += f"""
                <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:1.5em; margin-bottom:1em;">
                    <span style="color:#8b949e; font-size:0.8em; text-transform:uppercase;">{r['type']}</span><br>
                    <a href="{r['url']}" style="color:#00ff41; font-size:1.2em; font-weight:bold; text-decoration:none;">{r['title']}</a>
                    <p style="color:#c9d1d9; margin-top:0.5em; font-size:0.9em;">{r['snippet']}</p>
                </div>
                """
    
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Erebos Search</title>
  <style>
    body {{ background: #0d1117; color: #c9d1d9; font-family: sans-serif; padding: 2em; text-align: center; }}
    .search-box {{ margin: 3em auto; max-width: 600px; display: flex; gap: 10px; }}
    input[type="text"] {{ flex: 1; padding: 1em; background: #161b22; border: 1px solid #30363d; color: #00ff41; font-family: monospace; border-radius: 4px; font-size: 1.1em; }}
    button {{ padding: 1em 2em; background: #00ff41; color: #000; border: none; font-weight: bold; border-radius: 4px; cursor: pointer; }}
    .results {{ max-width: 800px; margin: 0 auto; text-align: left; }}
    h1 {{ color: #00ff41; font-family: monospace; letter-spacing: 0.1em; }}
  </style>
</head>
<body>
  <h1>EREBOS SEARCH</h1>
  <p style="color: #8b949e;">Durchsuche das gesamte Erebos-Netzwerk.</p>
  
  <form method="GET" action="/search" class="search-box">
    <input type="text" name="q" value="{query}" placeholder="Suche nach Threads, Wiki-Einträgen..." autofocus>
    <button type="submit">Suchen</button>
  </form>

  <div class="results">
    {results_html}
  </div>
  
  <p style="margin-top:3em;"><a href="/" style="color:#8b949e;">← Zurück zur Startseite</a></p>
  <p style="color:#30363d; font-size:0.8em;">Diese Instanz: {address}</p>
</body>
</html>"""
    return html.encode("utf-8")
