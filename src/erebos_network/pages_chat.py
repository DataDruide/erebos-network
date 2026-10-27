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
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: #050508; color: #00ff88;
  font-family: 'Courier New', 'Monaco', monospace;
  min-height: 100vh; padding: 2em;
}
.container { max-width: 900px; margin: 0 auto; }
h1 { color: #00ff88; font-size: 2em; letter-spacing: 0.2em; margin-bottom: 1em; }
h2 { color: #00ff88; font-size: 1.2em; letter-spacing: 0.15em; margin: 1.5em 0 0.8em; }
a { color: #00ff88; text-decoration: none; }
a:hover { text-decoration: underline; }
.box {
  border: 2px solid #00ff88; padding: 1.5em; margin: 1.5em 0;
  background: #0a0a15;
}
.btn {
  display: inline-block; padding: 0.8em 1.5em; margin: 0.5em 0.5em 0.5em 0;
  border: 2px solid #00ff88; background: transparent; color: #00ff88;
  font-family: inherit; font-size: 1em; cursor: pointer;
}
.btn:hover { background: #00ff88; color: #050508; }
input[type=text] {
  padding: 0.8em; width: 100%; max-width: 400px; margin: 0.5em 0;
  background: #0a0a15; border: 2px solid #00ff88; color: #00ff88;
  font-family: inherit; font-size: 1em;
}
.messages {
  height: 400px; overflow-y: auto; padding: 1em;
  border: 1px solid #00ff88; background: #0a0a15;
  margin-bottom: 1em;
}
.msg { margin: 0.5em 0; padding: 0.5em; border-left: 3px solid #00ff88; }
.msg.me { border-left-color: #ff8800; color: #ffcc88; }
.msg .meta { font-size: 0.75em; color: #888; }
.status { padding: 1em; text-align: center; }
.status.waiting { color: #ffcc00; }
.status.matched { color: #00ff88; }
.footer { margin-top: 4em; text-align: center; font-size: 0.8em; color: #666; word-break: break-all; }
.error { color: #ff4444; border-color: #ff4444; }
"""


def _html(title: str, body: str, address: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>EREBOS CHAT - {title}</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="container">
{body}
<p class="footer">{address}</p>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Startseite
# ---------------------------------------------------------------------------

def render_start(address: str) -> str:
    body = """
<h1>EREBOS CHAT</h1>
<div class="box">
  <h2>Random Chat</h2>
  <p style="margin-bottom:1em;">Werde mit einem zufaelligen Gespraechspartner verbunden.</p>
  <a class="btn" href="/chat/random">Random Chat starten</a>
</div>
<div class="box">
  <h2>Raum erstellen</h2>
  <p style="margin-bottom:1em;">Erstelle einen Raum und teile die ID mit deinem Partner.</p>
  <form method="POST" action="/chat/create">
    <button class="btn" type="submit">Raum erstellen</button>
  </form>
</div>
<div class="box">
  <h2>Raum beitreten</h2>
  <p style="margin-bottom:1em;">Gib die Raum-ID ein, die du von deinem Partner bekommen hast.</p>
  <form method="POST" action="/chat/join">
    <input type="text" name="room_id" placeholder="z.B. a1b2c3d4" maxlength="8">
    <button class="btn" type="submit">Beitreten</button>
  </form>
</div>
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
