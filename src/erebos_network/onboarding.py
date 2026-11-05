"""Onboarding-Flow: Echter Verbindungsaufbau (Terminal) + Welcome-Seite."""

import logging

logger = logging.getLogger(__name__)


def render_onboard(anon_uuid, address, _page, _escape):
    """Detaillierter Verbindungsaufbau mit Fortschrittsanzeige (Wow-Effekte)."""
    terminal_html = """
    <style>
      .terminal { background: #050508; color: #00ff88; font-family: 'Courier New', monospace; padding: 2em; border: 1px solid #00ff88; border-radius: 8px; max-width: 800px; margin: 2em auto; text-align: left; box-shadow: 0 0 20px rgba(0,255,136,0.2); position: relative; overflow: hidden; z-index: 1; }
      .terminal::before { content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: repeating-linear-gradient(0deg, rgba(0,255,136,0.03) 0px, rgba(0,255,136,0.03) 1px, transparent 1px, transparent 3px); pointer-events: none; }
      .log-line { margin: 0.8em 0; display: none; font-size: 0.9em; opacity: 0.7; }
      .log-line.active { display: block; animation: slideIn 0.4s ease; color: #00ff88; text-shadow: 0 0 8px rgba(0,255,136,0.6); }
      .log-line.done { opacity: 0.5; color: #888; text-shadow: none; }
      .success { color: #00ff88; font-weight: bold; text-shadow: 0 0 10px rgba(0,255,136,0.8); }
      .progress-container { margin-top: 2em; display: none; }
      .progress-container.active { display: block; animation: fadeIn 0.5s; }
      .progress-bar { width: 100%; height: 8px; background: #111; border-radius: 4px; overflow: hidden; margin-bottom: 0.5em; box-shadow: inset 0 1px 3px rgba(0,0,0,0.5); }
      .progress-fill { width: 0%; height: 100%; background: linear-gradient(90deg, #00ff88, #00ffcc); transition: width 0.5s ease; box-shadow: 0 0 10px #00ff88, 0 0 20px #00ff88; }
      .progress-text { text-align: right; font-size: 0.85em; color: #00ff88; text-shadow: 0 0 5px rgba(0,255,136,0.5); }
      .cursor { display: inline-block; width: 0.6em; height: 1em; background: #00ff88; margin-left: 4px; animation: blink 1s infinite; vertical-align: text-bottom; }
      .particle { position: fixed; width: 4px; height: 4px; background: #00ffcc; border-radius: 50%; pointer-events: none; box-shadow: 0 0 6px #00ffcc; animation: particleFloat 0.8s ease-out forwards; z-index: 1000; }
      @keyframes blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }
      @keyframes slideIn { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }
      @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
      @keyframes glowPulse { 0%, 100% { box-shadow: 0 0 10px #00ff88, 0 0 20px #00ff88; } 50% { box-shadow: 0 0 20px #00ff88, 0 0 40px #00ff88; } }
      @keyframes particleFloat { 0% { opacity: 1; transform: translate(0, 0) scale(1); } 100% { opacity: 0; transform: translate(var(--dx), var(--dy)) scale(0); } }
    </style>
    <canvas id="matrix-canvas" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0; opacity: 0.12; pointer-events: none;"></canvas>
    <div class="terminal">
      <div id="logs"></div>
      <div class="progress-container" id="progress-container">
        <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
        <div class="progress-text" id="progress-text">0%</div>
      </div>
    </div>
    <script>
      (function() {
        const canvas = document.getElementById('matrix-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        const chars = '01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン';
        const fontSize = 14;
        const columns = Math.floor(canvas.width / fontSize);
        const drops = Array(columns).fill(1);
        function drawMatrix() {
          ctx.fillStyle = 'rgba(5, 5, 8, 0.05)';
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = '#ff3333';
          ctx.font = fontSize + 'px monospace';
          for (let i = 0; i < drops.length; i++) {
            const text = chars[Math.floor(Math.random() * chars.length)];
            ctx.fillText(text, i * fontSize, drops[i] * fontSize);
            if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
              drops[i] = 0;
            }
            drops[i]++;
          }
        }
        setInterval(drawMatrix, 50);
      })();

      let audioCtx = null;
      function playPling(freq) {
        try {
          if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
          }
          const osc = audioCtx.createOscillator();
          const gain = audioCtx.createGain();
          osc.connect(gain);
          gain.connect(audioCtx.destination);
          osc.frequency.value = freq;
          osc.type = 'sine';
          gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.25);
          osc.start();
          osc.stop(audioCtx.currentTime + 0.25);
        } catch (e) {}
      }

      function spawnParticles(el) {
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const x = rect.right;
        const y = rect.top + rect.height / 2;
        for (let i = 0; i < 6; i++) {
          const p = document.createElement('div');
          p.className = 'particle';
          p.style.left = x + 'px';
          p.style.top = y + 'px';
          p.style.setProperty('--dx', (Math.random() * 80 + 20) + 'px');
          p.style.setProperty('--dy', (Math.random() - 0.5) * 60 + 'px');
          document.body.appendChild(p);
          setTimeout(() => p.remove(), 800);
        }
      }

      const logsDiv = document.getElementById('logs');
      const progressContainer = document.getElementById('progress-container');
      const progressFill = document.getElementById('progress-fill');
      const progressText = document.getElementById('progress-text');

      let displayedSteps = new Set();
      let totalMs = 0;
      let maxMs = 1000;

      async function pollTunnelTiming() {
        try {
          const resp = await fetch('/api/tunnel-timing');
          if (resp.status !== 200) return;
          const data = await resp.json();
          if (!data.steps || data.steps.length === 0) return;

          totalMs = data.total_ms || 0;
          if (totalMs > maxMs) maxMs = totalMs * 1.2;

          for (let i = 0; i < data.steps.length; i++) {
            const step = data.steps[i];
            const key = step.name + '|' + step.ms;
            if (displayedSteps.has(key)) continue;
            displayedSteps.add(key);

            await new Promise(r => setTimeout(r, 700));

            const line = document.createElement('div');
            line.className = 'log-line active';
            if (step.name === 'Rendezvous-Paar') line.className += ' success';
            line.innerText = '> ' + step.name + ' (' + Math.round(step.ms) + 'ms)';
            logsDiv.appendChild(line);

            playPling(880 + i * 40);

            const percent = Math.round(((i + 1) / data.steps.length) * 100);
            progressContainer.classList.add('active');
            progressFill.style.width = percent + '%';
            progressText.innerText = percent + '%';
            spawnParticles(progressFill);
          }

          const hasRendezvous = data.steps.some(s => s.name === 'Rendezvous-Paar');
          if (hasRendezvous) {
            document.querySelectorAll('.log-line').forEach(l => {
              l.classList.remove('active');
              l.classList.add('done');
            });

            const totalLine = document.createElement('div');
            totalLine.className = 'log-line active success';
            totalLine.innerText = '> Verbindung hergestellt in ' + Math.round(data.total_ms) + 'ms';
            logsDiv.appendChild(totalLine);

            const cursor = document.createElement('span');
            cursor.className = 'cursor';
            totalLine.appendChild(cursor);

            progressFill.style.width = '100%';
            progressText.innerText = '100% — Verbunden';
            progressFill.style.animation = 'glowPulse 1.5s infinite';

            playPling(1320);
            spawnParticles(progressFill);

            setTimeout(() => { window.location.href = '/welcome'; }, 2500);
            return;
          }
        } catch (e) {}
        setTimeout(pollTunnelTiming, 500);
      }

      setTimeout(pollTunnelTiming, 500);
    </script>
    """
    return _page("Verbinde...", address, terminal_html)


def render_welcome_onboarded(anon_uuid, address, _page, _escape):
    """Willkommens-Seite: UUID, E-Mail, Forum-Username, Warnung (modern, rot)."""
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

    body = (
        '<header style="text-align:center; margin-bottom:2em;">'
        '<img src="/static/hacker.jpeg" alt="Avatar" '
        'style="width:100px; height:100px; border-radius:50%; border:3px solid #ff3333; object-fit:cover;">'
        '<h1 style="color:#ff3333; margin-top:1em; text-shadow:0 0 20px rgba(255,51,51,0.3);">WILLKOMMEN BEI EREBOS</h1>'
        '</header>'

        '<div style="background:rgba(255,51,51,0.08); border-left:4px solid #ff3333; '
        'padding:12px 16px; border-radius:4px; margin-bottom:1.5em; font-size:0.85em; color:#ffcccc; '
        'display:flex; align-items:center; gap:10px;">'
        '<span style="font-size:1.2em;">🔒</span>'
        '<span><strong>Maximale Privatsphaere:</strong> E2E-verschluesselt - Keine Logs - Anonym - Kein Tracking</span>'
        '</div>'

        '<div style="background:#0d1117; border:1px solid #30363d; border-radius:8px; '
        'padding:1.5em; margin:1.5em 0;">'
        '<p style="color:#ff3333; font-size:0.85em; letter-spacing:0.15em; margin-bottom:1em; '
        'text-transform:uppercase;">DEINE IDENTITAET</p>'

        '<p style="margin:0.8em 0; color:#e6edf3;"><strong>UUID:</strong><br>'
        '<code style="color:#ff6666; word-break:break-all; font-family:inherit;">' + _escape(anon_uuid) + '</code></p>'

        '<p style="margin:0.8em 0; color:#e6edf3;"><strong>E-Mail:</strong><br>'
        '<code style="color:#ff6666; font-family:inherit;">' + _escape(email) + '</code></p>'

        '<p style="margin:0.8em 0; color:#e6edf3;"><strong>Forum:</strong><br>'
        '<code style="color:#ff6666; font-family:inherit;">' + _escape(forum_username) + '</code></p>'
        '</div>'

        '<div style="background:rgba(255,51,51,0.08); border-left:4px solid #ff3333; '
        'padding:1.5em; border-radius:8px; margin:1.5em 0;">'
        '<p style="color:#ff3333; font-size:0.85em; letter-spacing:0.1em; margin-bottom:0.8em; '
        'text-transform:uppercase;">WICHTIG - SCHREIB DAS AUF</p>'
        '<p style="color:#ffcccc; margin:0.5em 0; line-height:1.6;">'
        'Diese Daten werden <strong style="color:#fff;">nicht dauerhaft</strong> gespeichert. '
        'Nach einem Browser-Neustart sind sie <strong style="color:#fff;">verloren</strong>. '
        'Notiere UUID und E-Mail-Adresse jetzt.'
        '</p>'
        '</div>'

        '<form method="POST" action="/welcome/ack" style="margin:2em 0; text-align:center;">'
        '<button type="submit" style="background:#da3633; color:#fff; font-weight:600; '
        'padding:1em 2em; border:1px solid #ff3333; border-radius:6px; cursor:pointer; '
        'font-size:1em; font-family:inherit; transition:background-color 0.3s ease, border-color 0.3s ease;">'
        'Ich habe es aufgeschrieben'
        '</button>'
        '</form>'

        '<p style="text-align:center; margin-top:1em;">'
        '<a href="/mail" style="color:#ff3333; margin-right:1em; text-decoration:none; '
        'border:1px solid #30363d; padding:0.5em 1em; border-radius:6px; display:inline-block; '
        'background:#21262d; transition:background-color 0.3s ease, border-color 0.3s ease;">'
        '→ Zum Postfach</a> '
        '<a href="/forum" style="color:#ff3333; text-decoration:none; '
        'border:1px solid #30363d; padding:0.5em 1em; border-radius:6px; display:inline-block; '
        'background:#21262d; transition:background-color 0.3s ease, border-color 0.3s ease;">'
        '→ Zum Forum</a>'
        '</p>'
    )
    return _page("Willkommen", address, body)



def render_recover(address, _page, _escape, error=""):
    """Recovery-Seite: Formular fuer UUID/E-Mail-Eingabe."""
    body = (
        '<h1>Identitaet wiederherstellen</h1>'
        '<p style="color:#a0a0b0; margin:1em 0;">'
        'Gib deine UUID oder E-Mail-Adresse ein, um deine Identitaet '
        'wiederherzustellen.</p>'
        + (f'<p style="color:#ff4060;">{error}</p>' if error else '') +
        '<form method="POST" action="/recover" style="margin:2em 0;">'
        '<p><label>UUID oder E-Mail:<br>'
        '<input type="text" name="identifier" '
        'style="width:100%; padding:0.6em; margin-top:0.3em; '
        'background:#1a1a24; border:1px solid #2a2a3a; color:#e0e0e8; '
        'border-radius:4px;" required></label></p>'
        '<button type="submit" class="btn" '
        'style="background:#00ff88; color:#000; font-weight:bold; '
        'padding:0.8em 1.5em; border:none; border-radius:4px; '
        'cursor:pointer; margin-top:1em;">Wiederherstellen</button>'
        '</form>'
        '<p><a href="/onboard">Neu starten</a></p>'
    )
    return _page("Identitaet wiederherstellen", address, body)
