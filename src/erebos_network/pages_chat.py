"""HTML-Renderer fuer den Erebos-Chat.

Routen:
  /                       Startseite (Random / Raum erstellen / Raum-ID)
  /chat/random            Warteschlange (pollt /chat/random/status)
  /chat/room/<id>         Chat-Raum (pollt /chat/room/<id>/messages)
  /chat/create            POST -> redirect zu /chat/room/<id>
  /chat/join              POST -> redirect zu /chat/room/<id>
"""

from . import chat


# ---------------------------------------------------------------------------
# CSS (identisch zum Onboarding-Stil: schwarz, neongruen, Monospace)
# ---------------------------------------------------------------------------

_CSS = """
:root {
  --bg: #050508; --bg-card: #0d0d14; --bg-card-hover: #14141f;
  --fg: #c8d8c8; --fg-dim: #7a8a7a;
  --accent: #4ade80; --accent-dim: #22c55e33;
  --warn: #fbbf24; --danger: #f87171; --border: #1f2937;
  --mono: 'Courier New', 'Monaco', monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background: var(--bg); color: var(--fg); font-family: var(--mono);
  font-size: 15px; line-height: 1.7; min-height: 100vh; padding: 2rem 1rem;
}
body::before {
  content: ''; position: fixed; inset: 0;
  background:
    radial-gradient(circle at 20% 20%, #4ade8010 0%, transparent 50%),
    radial-gradient(circle at 80% 80%, #4ade8008 0%, transparent 50%);
  pointer-events: none; z-index: -1;
}
.container { max-width: 960px; margin: 0 auto; }
header { text-align: center; margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--border); }
h1 { font-size: 2rem; color: var(--accent); letter-spacing: 2px; text-transform: uppercase; margin-bottom: .5rem; text-shadow: 0 0 20px var(--accent-dim); }
.subtitle { color: var(--fg-dim); font-size: .85rem; }
.tabs { display: flex; gap: .5rem; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: .5rem; flex-wrap: wrap; }
.tab { background: transparent; border: 1px solid var(--border); color: var(--fg-dim); padding: .5rem 1rem; font-family: var(--mono); font-size: .9rem; cursor: pointer; border-radius: 6px; transition: all .2s; }
.tab:hover { border-color: var(--accent); color: var(--fg); }
.tab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
.panel { display: none; }
.panel.active { display: block; animation: fadeIn .3s; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; }
.card h2 { color: var(--accent); font-size: 1rem; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 1px; }
.card p { color: var(--fg-dim); font-size: .85rem; margin-bottom: 1rem; }
.btn { display: inline-block; padding: .7rem 1.4rem; margin: .3rem .3rem .3rem 0; border: 1px solid var(--accent); background: var(--accent-dim); color: var(--accent); font-family: var(--mono); font-size: .9rem; font-weight: bold; border-radius: 6px; cursor: pointer; text-decoration: none; transition: all .2s; }
.btn:hover { background: var(--accent); color: var(--bg); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-secondary { background: transparent; border-color: var(--border); color: var(--fg-dim); }
.btn-secondary:hover { border-color: var(--accent); color: var(--fg); background: transparent; }
input[type=text] { width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--fg); padding: .7rem 1rem; font-family: var(--mono); font-size: .9rem; border-radius: 6px; transition: border-color .2s; margin-bottom: .8rem; }
input[type=text]:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.copy-btn { background: var(--accent-dim); border: 1px solid var(--accent); color: var(--accent); padding: .2rem .6rem; margin-left: .5rem; border-radius: 4px; cursor: pointer; font-size: .75rem; font-family: var(--mono); transition: all .2s; }
.copy-btn:hover { background: var(--accent); color: var(--bg); }
.room-id { display: inline-block; background: var(--bg); border: 1px solid var(--accent); color: var(--accent); padding: .3rem .6rem; border-radius: 4px; font-family: var(--mono); font-size: .85rem; word-break: break-all; }
.empty-state { text-align: center; padding: 2rem 1rem; color: var(--fg-dim); }
.empty-state .icon { font-size: 2.5rem; margin-bottom: .5rem; opacity: .5; }
.key-status { display: flex; align-items: center; gap: .5rem; margin-bottom: 1rem; }
.key-status .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 8px var(--accent); animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.footer { text-align: center; padding-top: 2rem; margin-top: 2rem; border-top: 1px solid var(--border); color: var(--fg-dim); font-size: .8rem; }
.footer a { color: var(--accent); text-decoration: none; border-bottom: 1px dashed var(--accent); }
.instance { margin-top: .5rem; font-size: .75rem; word-break: break-all; }
.toast { position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%) translateY(100px); background: var(--accent); color: var(--bg); padding: .7rem 1.4rem; border-radius: 6px; font-weight: bold; font-size: .85rem; opacity: 0; transition: transform .3s, opacity .3s; pointer-events: none; z-index: 1000; }
.toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
.toast.error { background: var(--danger); color: #fff; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
"""


def _html(title: str, body: str, address: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Erebos Chat - {title}</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Erebos Chat</h1>
    <p class="subtitle">Sichere Echtzeit-Kommunikation im Erebos-Netzwerk</p>
  </header>
{body}
  <footer class="footer">
    <a href="/">← Startseite</a>
    <div class="instance" id="instance">{address}</div>
  </footer>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>
(() => {{
  'use strict';
  const toast = document.getElementById('toast');
  let toastTimer;
  window.showToast = (msg, isError=false) => {{
    toast.textContent = msg;
    toast.classList.toggle('error', isError);
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3000);
  }};
  // Tabs
  document.querySelectorAll('.tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const panel = document.getElementById('panel-' + tab.dataset.tab);
      if (panel) panel.classList.add('active');
    }});
  }});
  // Copy-Buttons
  document.querySelectorAll('.copy-btn').forEach(btn => {{
    btn.addEventListener('click', async (e) => {{
      e.stopPropagation();
      try {{
        await navigator.clipboard.writeText(btn.dataset.copy);
        window.showToast('Kopiert!');
      }} catch {{
        window.showToast('Kopieren fehlgeschlagen', true);
      }}
    }});
  }});
}})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Startseite
# ---------------------------------------------------------------------------

def render_start(address: str) -> str:
    body = """
  <div class="tabs" role="tablist">
    <button class="tab active" data-tab="random" role="tab">🎲 Random Chat</button>
    <button class="tab" data-tab="create" role="tab">➕ Raum erstellen</button>
    <button class="tab" data-tab="join" role="tab">🔗 Raum beitreten</button>
    <button class="tab" data-tab="active" role="tab">💬 Aktive Räume</button>
  </div>

  <div class="panel active" id="panel-random">
    <div class="card">
      <h2>Random Chat</h2>
      <p>Werde mit einem zufälligen Gesprächspartner verbunden.</p>
      <a class="btn" href="/chat/random" id="random-btn">Random Chat starten</a>
    </div>
  </div>

  <div class="panel" id="panel-create">
    <div class="card">
      <h2>Raum erstellen</h2>
      <p>Erstelle einen Raum und teile die ID mit deinem Partner.</p>
      <form method="POST" action="/chat/create" id="create-form">
        <button class="btn" type="submit" id="create-btn">Raum erstellen</button>
      </form>
    </div>
  </div>

  <div class="panel" id="panel-join">
    <div class="card">
      <h2>Raum beitreten</h2>
      <p>Gib die Raum-ID ein, die du von deinem Partner bekommen hast.</p>
      <form method="POST" action="/chat/join" id="join-form">
        <input type="text" name="room_id" id="room-id-input" placeholder="z.B. a1b2c3d4" maxlength="8" autocomplete="off">
        <button class="btn" type="submit" id="join-btn">Beitreten</button>
      </form>
    </div>
  </div>

  <div class="panel" id="panel-active">
    <div class="card">
      <h2>Aktive Räume</h2>
      <div id="active-rooms">
        <div class="empty-state">
          <div class="icon">💬</div>
          <p>Kein aktiver Chat.</p>
          <p style="font-size:.8rem;margin-top:.5rem;">Starte einen Random Chat oder tritt einem Raum bei.</p>
        </div>
      </div>
    </div>
  </div>

  <script>
  (() => {
    // Room-ID-Validierung
    const input = document.getElementById('room-id-input');
    const joinBtn = document.getElementById('join-btn');
    if (input && joinBtn) {
      input.addEventListener('input', () => {
        const ok = /^[a-zA-Z0-9]{4,8}$/.test(input.value.trim());
        joinBtn.disabled = !ok;
        input.style.borderColor = ok ? 'var(--accent)' : 'var(--border)';
      });
    }

    // Loading-State bei Random/Create
    document.getElementById('random-btn')?.addEventListener('click', (e) => {
      e.preventDefault();
      const btn = e.target;
      btn.textContent = 'Verbinde…';
      btn.style.opacity = '.7';
      window.location.href = '/chat/random';
    });
    document.getElementById('create-btn')?.addEventListener('click', (e) => {
      const btn = e.target;
      btn.textContent = 'Erstelle…';
      btn.disabled = true;
    });

    // Letzte Räume aus localStorage
    const container = document.getElementById('active-rooms');
    if (container) {
      try {
        const rooms = JSON.parse(localStorage.getItem('erebos_recent_rooms') || '[]');
        if (rooms.length > 0) {
          container.innerHTML = '';
          rooms.slice(0, 5).forEach(room => {
            const div = document.createElement('div');
            div.className = 'card';
            div.style.padding = '0.8rem';
            div.innerHTML = `
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span class="room-id">${room}</span>
                <a class="btn btn-secondary" href="/chat/room/${room}">Öffnen</a>
              </div>
            `;
            container.appendChild(div);
          });
        }
      } catch {}
    }
  })();
  </script>
"""
    return _html("Start", body, address)


# ---------------------------------------------------------------------------
# Warteschlange (Random)
# ---------------------------------------------------------------------------

def render_random_waiting(address: str) -> str:
    body = """
<h1>WARTESCHLANGE</h1>
<div class="box">
  <p class="status waiting" id="status">Suche Gespraechspartner...</p>
  <p style="margin-top:1em;"><a href="/" class="btn">Abbrechen</a></p>
</div>
<script>
async function poll() {
  try {
    const r = await fetch('/chat/random/status');
    const d = await r.json();
    if (d.matched) {
      window.location.href = '/chat/room/' + d.matched;
      return;
    }
  } catch (e) {}
  setTimeout(poll, 1500);
}
poll();
</script>
"""
    return _html("Warte", body, address)


# ---------------------------------------------------------------------------
# Chat-Raum
# ---------------------------------------------------------------------------

def render_room(room_id: str, address: str, cookie: str) -> str:
    body = f"""
<h1>RAUM {room_id}</h1>
<div class="box">
  <p style="margin-bottom:1em;">Teile diese URL mit deinem Partner:</p>
  <code style="word-break:break-all; color:#00ff88;">http://{address}/chat/room/{room_id}</code>
</div>
<div class="box">
  <div class="messages" id="messages"></div>
  <form id="sendform" method="POST" action="/chat/room/{room_id}/send">
    <input type="text" name="message" placeholder="Nachricht..." autocomplete="off">
    <button class="btn" type="submit">Senden</button>
  </form>
</div>
<script>
const MY_COOKIE = "{cookie}";
let since = 0;
async function poll() {{
  try {{
    const r = await fetch('/chat/room/{room_id}/messages?since=' + since);
    const msgs = await r.json();
    const box = document.getElementById('messages');
    for (const m of msgs) {{
      since = Math.max(since, m.ts);
      const div = document.createElement('div');
      div.className = 'msg' + (m.from === MY_COOKIE ? ' me' : '');
      div.innerHTML = '<div class="meta">' +
        (m.from === MY_COOKIE ? 'Du' : 'Partner') +
        ' · ' + new Date(m.ts * 1000).toLocaleTimeString() + '</div>' +
        '<div>' + m.text.replace(/[<>&]/g, c => ({{'<':'&lt;','>':'&gt;','&':'&amp;'}})[c]) + '</div>';
      box.appendChild(div);
    }}
    box.scrollTop = box.scrollHeight;
  }} catch (e) {{}}
  setTimeout(poll, 1500);
}}
poll();
</script>
"""
    return _html(f"Raum {room_id}", body, address)


# ---------------------------------------------------------------------------
# Fehlerseite
# ---------------------------------------------------------------------------

def render_error(address: str, message: str) -> str:
    body = f"""
<h1>FEHLER</h1>
<div class="box error">
  <p>{message}</p>
  <p style="margin-top:1em;"><a href="/" class="btn">Zurueck</a></p>
</div>
"""
    return _html("Fehler", body, address)
