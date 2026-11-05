"""Erebos-Theme: Matrix-Regen, Scanlines, Vignette, Custom Cursor, Live-Peers."""


def render_theme_head() -> str:
    return """
    <style>
      #matrix-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; opacity: 0.08; pointer-events: none; }
      body::after { content: ''; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: repeating-linear-gradient(0deg, rgba(255,51,51,0.02) 0px, rgba(255,51,51,0.02) 1px, transparent 1px, transparent 3px); pointer-events: none; z-index: 9998; }
      body::before { content: ''; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%); pointer-events: none; z-index: 9997; }
      body { cursor: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="8" height="16" fill="%23ff3333"/></svg>') 0 0, auto; }
      .erebos-identity { position: fixed; top: 10px; right: 10px; background: rgba(5,5,8,0.9); border: 1px solid #ff3333; border-radius: 4px; padding: 6px 12px; font-family: 'Courier New', monospace; font-size: 0.75em; color: #ff3333; z-index: 9999; text-shadow: 0 0 5px rgba(255,51,51,0.5); box-shadow: 0 0 10px rgba(255,51,51,0.2); }
      .erebos-identity .handle { color: #ffcccc; font-weight: bold; }
      .erebos-identity .addr { color: #ff6666; font-size: 0.7em; display: block; margin-top: 2px; }
      .erebos-identity .peers { color: #ff9999; font-size: 0.7em; display: block; margin-top: 2px; }
      .erebos-identity .pulse { display: inline-block; width: 6px; height: 6px; background: #ff3333; border-radius: 50%; margin-right: 4px; animation: pulse 1.5s infinite; }
      @keyframes pulse { 0%, 100% { opacity: 1; box-shadow: 0 0 4px #ff3333; } 50% { opacity: 0.3; box-shadow: 0 0 8px #ff3333; } }
      /* Glitch beim Seitenwechsel */
      body.glitch { animation: glitchAnim 0.3s; }
      @keyframes glitchAnim {
        0% { filter: none; transform: translate(0); }
        20% { filter: hue-rotate(90deg) saturate(3); transform: translate(-2px, 2px); }
        40% { filter: hue-rotate(-90deg) saturate(3); transform: translate(2px, -2px); }
        60% { filter: invert(1); transform: translate(-1px, 1px); }
        80% { filter: hue-rotate(180deg); transform: translate(1px, -1px); }
        100% { filter: none; transform: translate(0); }
      }
      /* Erebos-Zeit */
      .erebos-time { position: fixed; bottom: 10px; right: 10px; background: rgba(5,5,8,0.9); border: 1px solid #ff3333; border-radius: 4px; padding: 4px 10px; font-family: 'Courier New', monospace; font-size: 0.7em; color: #ff6666; z-index: 9999; }
      /* Achievements (Toasts) */
      .achievement-toast { position: fixed; bottom: 60px; left: 20px; background: rgba(5,5,8,0.95); border: 1px solid #ff3333; border-radius: 6px; padding: 12px 20px; font-family: 'Courier New', monospace; font-size: 0.85em; color: #ffcccc; z-index: 10000; box-shadow: 0 0 20px rgba(255,51,51,0.5); transform: translateX(-120%); transition: transform 0.5s ease; max-width: 300px; }
      .achievement-toast.show { transform: translateX(0); }
      .achievement-toast .title { color: #ff3333; font-weight: bold; font-size: 0.9em; margin-bottom: 4px; }
      .achievement-toast .desc { color: #ff9999; font-size: 0.8em; }
      .achievement-toast .icon { font-size: 1.5em; margin-right: 10px; }
      /* Netzwerk-Karte (unten links) */
      .network-map { position: fixed; bottom: 100px; left: 20px; width: 200px; height: 150px; background: rgba(5,5,8,0.9); border: 1px solid #ff3333; border-radius: 6px; z-index: 9998; box-shadow: 0 0 15px rgba(255,51,51,0.3); overflow: hidden; cursor: pointer; transition: all 0.3s; }
      .network-map:hover { width: 300px; height: 220px; box-shadow: 0 0 25px rgba(255,51,51,0.6); }
      .network-map canvas { width: 100%; height: 100%; display: block; }
      .network-map .label { position: absolute; top: 4px; left: 8px; font-family: 'Courier New', monospace; font-size: 0.65em; color: #ff6666; text-shadow: 0 0 5px rgba(255,51,51,0.5); }
    </style>
    <canvas id="matrix-canvas"></canvas>
    """


def render_theme_script() -> str:
    return """
    <script>
      (function() {
        const canvas = document.getElementById('matrix-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
        resize();
        window.addEventListener('resize', resize);
        const chars = '01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン';
        const fontSize = 14;
        let columns = Math.floor(canvas.width / fontSize);
        let drops = Array(columns).fill(1);
        function drawMatrix() {
          ctx.fillStyle = 'rgba(5, 5, 8, 0.05)';
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = '#ff3333';
          ctx.font = fontSize + 'px monospace';
          for (let i = 0; i < drops.length; i++) {
            const text = chars[Math.floor(Math.random() * chars.length)];
            ctx.fillText(text, i * fontSize, drops[i] * fontSize);
            if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0;
            drops[i]++;
          }
        }
        setInterval(drawMatrix, 50);
      })();
      (function() {
        const peersEl = document.getElementById('erebos-peers');
        if (!peersEl) return;
        async function pollPeers() {
          try {
            const resp = await fetch('/api/status');
            if (resp.status !== 200) return;
            const data = await resp.json();
            let ok = 0, total = 0;
            for (const k in data) { total++; if (data[k].ok) ok++; }
            peersEl.innerText = ok + '/' + total + ' Dienste online';
          } catch (e) {}
        }
        pollPeers();
        setInterval(pollPeers, 10000);
      })();

      // Glitch beim Seitenwechsel
      document.addEventListener('click', function(e) {
        const a = e.target.closest('a');
        if (a && a.href && a.href.startsWith(location.origin)) {
          e.preventDefault();
          document.body.classList.add('glitch');
          playClick();
          setTimeout(() => { window.location.href = a.href; }, 300);
        }
      });

      // Sound: Klick + Ambient
      let ambientCtx = null;
      let ambientOsc = null;
      function playClick() {
        try {
          const ctx = new (window.AudioContext || window.webkitAudioContext)();
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.frequency.value = 1200;
          osc.type = 'square';
          gain.gain.setValueAtTime(0.05, ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.05);
          osc.start();
          osc.stop(ctx.currentTime + 0.05);
        } catch (e) {}
      }

      // Ambient-Sound (leises Rauschen) — startet beim ersten Klick
      function startAmbient() {
        if (ambientCtx) return;
        try {
          ambientCtx = new (window.AudioContext || window.webkitAudioContext)();
          ambientOsc = ambientCtx.createOscillator();
          const gain = ambientCtx.createGain();
          ambientOsc.connect(gain);
          gain.connect(ambientCtx.destination);
          ambientOsc.frequency.value = 60;
          ambientOsc.type = 'sine';
          gain.gain.value = 0.005;
          ambientOsc.start();
        } catch (e) {}
      }
      document.addEventListener('click', startAmbient, { once: true });

      // Erebos-Zeit (eigene Zeitrechnung)
      (function() {
        const timeEl = document.getElementById('erebos-time');
        if (!timeEl) return;
        function updateTime() {
          const now = new Date();
          // Erebos-Zeit: Start bei 2024-01-01, 1 Tick = 1 Sekunde
          const start = new Date('2024-01-01T00:00:00Z').getTime();
          const diff = Math.floor((now.getTime() - start) / 1000);
          const days = Math.floor(diff / 86400);
          const hours = Math.floor((diff % 86400) / 3600);
          const mins = Math.floor((diff % 3600) / 60);
          const secs = diff % 60;
          timeEl.innerText = 'Erebos-Zeit: Tag ' + days + ', ' + String(hours).padStart(2,'0') + ':' + String(mins).padStart(2,'0') + ':' + String(secs).padStart(2,'0');
        }
        updateTime();
        setInterval(updateTime, 1000);
      })();

      // Achievements (Toasts)
      (function() {
        const achievements = {
          'first_visit': { title: 'Willkommen in Erebos', desc: 'Du hast die verborgene Welt betreten.', icon: '🌐' },
          'wiki_reader': { title: 'Wissensdurstig', desc: 'Du hast das Hidden Wiki gelesen.', icon: '📖' },
          'forum_visitor': { title: 'Teil der Community', desc: 'Du hast das Forum betreten.', icon: '💬' },
          'mail_checker': { title: 'Postbote', desc: 'Du hast dein Postfach geöffnet.', icon: '📬' },
          'chat_joiner': { title: 'Gesprächig', desc: 'Du hast den Chat betreten.', icon: '🗣️' }
        };

        function showToast(id) {
          const a = achievements[id];
          if (!a) return;
          // Prüfen, ob schon gezeigt (localStorage)
          const shown = JSON.parse(localStorage.getItem('erebos_achievements') || '[]');
          if (shown.includes(id)) return;
          shown.push(id);
          localStorage.setItem('erebos_achievements', JSON.stringify(shown));

          // Toast erstellen
          const toast = document.createElement('div');
          toast.className = 'achievement-toast';
          toast.innerHTML = '<div class="title"><span class="icon">' + a.icon + '</span>' + a.title + '</div><div class="desc">' + a.desc + '</div>';
          document.body.appendChild(toast);

          // Einblenden
          setTimeout(() => toast.classList.add('show'), 100);
          // Ausblenden nach 5s
          setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 600);
          }, 5000);
        }

        // Erstbesuch
        showToast('first_visit');

        // Seiten-spezifische Achievements
        const path = location.pathname;
        if (path.includes('/wiki')) showToast('wiki_reader');
        if (path.includes('/forum')) showToast('forum_visitor');
        if (path.includes('/mail')) showToast('mail_checker');
        if (path.includes('/chat')) showToast('chat_joiner');
      })();

      // Netzwerk-Karte (Canvas — Peers als leuchtende Punkte)
      (function() {
        const canvas = document.getElementById('network-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        function resize() {
          const rect = canvas.parentElement.getBoundingClientRect();
          canvas.width = rect.width;
          canvas.height = rect.height;
        }
        resize();
        window.addEventListener('resize', resize);

        // Simulierte Peers (Positionen relativ zur Karte)
        const peers = [
          { x: 0.15, y: 0.3, name: 'peer1', active: true },
          { x: 0.5, y: 0.15, name: 'peer2', active: true },
          { x: 0.85, y: 0.35, name: 'peer3', active: true },
          { x: 0.7, y: 0.7, name: 'peer4', active: true },
          { x: 0.3, y: 0.8, name: 'peer5', active: false },
          { x: 0.5, y: 0.5, name: 'self', active: true, isSelf: true },
        ];

        let particles = [];
        function drawNetwork() {
          const w = canvas.width;
          const h = canvas.height;
          ctx.fillStyle = 'rgba(5,5,8,0.15)';
          ctx.fillRect(0, 0, w, h);

          // Linien zwischen Peers (vom self zu den anderen)
          const self = peers.find(p => p.isSelf);
          if (self) {
            ctx.strokeStyle = 'rgba(255,51,51,0.3)';
            ctx.lineWidth = 1;
            for (const p of peers) {
              if (p.isSelf) continue;
              ctx.beginPath();
              ctx.moveTo(self.x * w, self.y * h);
              ctx.lineTo(p.x * w, p.y * h);
              ctx.stroke();
            }
          }

          // Peers als leuchtende Punkte
          for (const p of peers) {
            const px = p.x * w;
            const py = p.y * h;
            const radius = p.isSelf ? 6 : 4;
            const color = p.isSelf ? '#ff3333' : (p.active ? '#00ff88' : '#666');
            // Glow
            const grad = ctx.createRadialGradient(px, py, 0, px, py, radius * 3);
            grad.addColorStop(0, color);
            grad.addColorStop(1, 'transparent');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(px, py, radius * 3, 0, Math.PI * 2);
            ctx.fill();
            // Kern
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(px, py, radius, 0, Math.PI * 2);
            ctx.fill();
            // Label
            ctx.fillStyle = '#ff9999';
            ctx.font = '8px monospace';
            ctx.fillText(p.name, px + 6, py + 3);
          }

          // Partikel (Datenfluss)
          if (Math.random() < 0.1) {
            const self = peers.find(p => p.isSelf);
            const other = peers.filter(p => !p.isSelf && p.active);
            if (self && other.length > 0) {
              const target = other[Math.floor(Math.random() * other.length)];
              particles.push({ sx: self.x, sy: self.y, tx: target.x, ty: target.y, t: 0 });
            }
          }
          particles = particles.filter(p => p.t < 1);
          for (const p of particles) {
            p.t += 0.02;
            const x = (p.sx + (p.tx - p.sx) * p.t) * w;
            const y = (p.sy + (p.ty - p.sy) * p.t) * h;
            ctx.fillStyle = 'rgba(255,51,51,' + (1 - p.t) + ')';
            ctx.beginPath();
            ctx.arc(x, y, 2, 0, Math.PI * 2);
            ctx.fill();
          }

          requestAnimationFrame(drawNetwork);
        }
        drawNetwork();
      })();
    </script>
    """


def render_identity_widget(address: str) -> str:
    handle = "anon-" + address[:8] if address else "anon-????"
    return f"""
    <div class="erebos-identity">
      <div><span class="pulse"></span><span class="handle">{handle}</span></div>
      <div class="addr">{address}</div>
      <div class="peers" id="erebos-peers">verbinde...</div>
    </div>
    <div class="erebos-time" id="erebos-time">Erebos-Zeit: ...</div>
    <div class="network-map">
      <div class="label">NETZWERK</div>
      <canvas id="network-canvas"></canvas>
    </div>
    """


def decorate_page(body: bytes, address: str) -> bytes:
    """Dekoriert eine HTML-Seite mit dem Erebos-Theme (head + script + identity)."""
    if not body or not body.lstrip().startswith(b"<"):
        return body
    try:
        html = body.decode("utf-8", errors="replace")
        if "</head>" in html:
            html = html.replace("</head>", render_theme_head() + "</head>", 1)
        else:
            html = render_theme_head() + html
        script_identity = render_identity_widget(address) + render_theme_script()
        if "</body>" in html:
            html = html.replace("</body>", script_identity + "</body>", 1)
        else:
            html += script_identity
        return html.encode("utf-8")
    except Exception:
        return body
