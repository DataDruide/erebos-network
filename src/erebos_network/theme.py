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
