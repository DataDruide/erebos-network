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
