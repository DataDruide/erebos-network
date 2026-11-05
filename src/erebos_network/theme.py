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
      /* Erebos-Level (oben rechts, unter der Identität) */
      .erebos-level { position: fixed; top: 90px; right: 10px; background: rgba(5,5,8,0.9); border: 1px solid #ff3333; border-radius: 4px; padding: 6px 12px; font-family: 'Courier New', monospace; font-size: 0.75em; color: #ff3333; z-index: 9999; text-shadow: 0 0 5px rgba(255,51,51,0.5); box-shadow: 0 0 10px rgba(255,51,51,0.2); min-width: 120px; }
      .erebos-level .level-num { color: #ffcccc; font-weight: bold; font-size: 1.1em; }
      .erebos-level .xp-bar { width: 100%; height: 4px; background: #111; border-radius: 2px; margin-top: 4px; overflow: hidden; }
      .erebos-level .xp-fill { height: 100%; background: linear-gradient(90deg, #ff3333, #ff6666); transition: width 0.5s ease; box-shadow: 0 0 5px #ff3333; }
      .erebos-level .xp-text { font-size: 0.65em; color: #ff9999; margin-top: 2px; }
      /* Erebos-Token (im Identity-Widget) */
      .erebos-token { display: flex; align-items: center; gap: 4px; color: #ffcc00; font-weight: bold; text-shadow: 0 0 5px rgba(255,204,0,0.5); margin-top: 4px; }
      .erebos-token .token-icon { font-size: 1.1em; }
      .erebos-token .token-amount { color: #ffee99; }
      .erebos-identity .links { margin-top: 6px; display: flex; gap: 8px; font-size: 0.7em; }
      .erebos-identity .links a { color: #ff9999; text-decoration: none; }
      .erebos-identity .links a:hover { color: #ffcccc; text-decoration: underline; }
      .erebos-identity .sound-toggle { cursor: pointer; user-select: none; }
      .erebos-identity .sound-toggle:hover { color: #ffcccc; }
      /* Profil-Panel (Slide-in von rechts) */
      .profile-panel { position: fixed; top: 0; right: -400px; width: 400px; height: 100vh; background: rgba(5,5,8,0.98); border-left: 2px solid #ff3333; z-index: 10001; transition: right 0.3s ease; overflow-y: auto; padding: 2em; box-shadow: -5px 0 30px rgba(255,51,51,0.3); font-family: 'Courier New', monospace; }
      .profile-panel.open { right: 0; }
      .profile-panel .close-btn { position: absolute; top: 1em; right: 1em; color: #ff3333; cursor: pointer; font-size: 1.5em; background: none; border: none; }
      .profile-panel .close-btn:hover { color: #ff6666; }
      .profile-panel .avatar { width: 100px; height: 100px; border-radius: 50%; border: 3px solid #ff3333; margin: 0 auto 1em; display: block; background: #1a0a0a; }
      .profile-panel h2 { color: #ff3333; text-align: center; margin-bottom: 0.5em; }
      .profile-panel .addr-full { color: #ff6666; font-size: 0.7em; word-break: break-all; text-align: center; margin-bottom: 1.5em; }
      .profile-panel .stat-row { display: flex; justify-content: space-between; padding: 0.5em 0; border-bottom: 1px solid #1a0a0a; }
      .profile-panel .stat-row .label { color: #ff9999; }
      .profile-panel .stat-row .value { color: #ffcccc; font-weight: bold; }
      .profile-panel .achievements-list { margin-top: 1em; }
      .profile-panel .achievement-item { padding: 0.5em; border-left: 2px solid #ff3333; margin-bottom: 0.5em; background: rgba(255,51,51,0.05); }
      .profile-panel .achievement-item .title { color: #ff3333; font-weight: bold; }
      .profile-panel .achievement-item .desc { color: #ff9999; font-size: 0.8em; }
      .profile-panel .panel-link { display: block; padding: 0.8em; margin: 0.5em 0; background: rgba(255,51,51,0.1); border: 1px solid #ff3333; border-radius: 4px; color: #ffcccc; text-decoration: none; text-align: center; }
      .profile-panel .panel-link:hover { background: rgba(255,51,51,0.2); }
      .profile-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 10000; opacity: 0; pointer-events: none; transition: opacity 0.3s; }
      .profile-overlay.open { opacity: 1; pointer-events: auto; }
    </style>
    <canvas id="matrix-canvas"></canvas>
    """


def render_theme_script() -> str:
    return """
    <script>
      (async function() {
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
      (async function() {
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

      // Sound-Toggle (an/aus)
      (async function() {
        const toggle = document.getElementById('sound-toggle');
        if (!toggle) return;
        let soundOn = localStorage.getItem('erebos_sound') !== 'off';
        toggle.innerText = soundOn ? '🔊' : '🔇';
        toggle.addEventListener('click', function(e) {
          e.stopPropagation();
          soundOn = !soundOn;
          localStorage.setItem('erebos_sound', soundOn ? 'on' : 'off');
          toggle.innerText = soundOn ? '🔊' : '🔇';
          if (!soundOn && ambientOsc) {
            try { ambientOsc.stop(); } catch(e) {}
            ambientOsc = null;
            ambientCtx = null;
          }
          if (soundOn) startAmbient();
        });
      })();

      // Erebos-Zeit (eigene Zeitrechnung)
      (async function() {
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
      (async function() {
        const achievements = {
          'first_visit': { title: 'Willkommen in Erebos', desc: 'Du hast die verborgene Welt betreten.', icon: '🌐' },
          'wiki_reader': { title: 'Wissensdurstig', desc: 'Du hast das Hidden Wiki gelesen.', icon: '📖' },
          'forum_visitor': { title: 'Teil der Community', desc: 'Du hast das Forum betreten.', icon: '💬' },
          'mail_checker': { title: 'Postbote', desc: 'Du hast dein Postfach geöffnet.', icon: '📬' },
          'chat_joiner': { title: 'Gesprächig', desc: 'Du hast den Chat betreten.', icon: '🗣️' }
        };

        async function showToast(id) {
          const a = achievements[id];
          if (!a) return;
          // Prüfen, ob schon gezeigt (localStorage)
          const shown = Array.isArray(achievements) ? achievements : [];
          if (shown.includes(id)) return;
          shown.push(id);
          try {
            await fetch('/api/progress', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({achievements: achievements})
            });
          } catch (e) {}

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
      (async function() {
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

        // Echte Peers (aus /api/peers)
        let peers = [];
        const selfPeer = { x: 0.5, y: 0.5, name: 'self', active: true, isSelf: true };
        async function loadPeers() {
          try {
            const resp = await fetch('/api/peers');
            if (!resp.ok) return;
            const data = await resp.json();
            const list = data.peers || [];
            const n = list.length;
            peers = list.map((p, i) => {
              const angle = (2 * Math.PI * i) / Math.max(n, 1) - Math.PI / 2;
              return {
                x: 0.5 + 0.35 * Math.cos(angle),
                y: 0.5 + 0.35 * Math.sin(angle),
                name: p.name || '?',
                active: p.enabled !== false,
                isSelf: false,
              };
            });
            peers.push(selfPeer);
          } catch (e) {
            peers = [selfPeer];
          }
        }
        loadPeers();
        // Peers alle 30s neu laden
        setInterval(loadPeers, 30000);

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

      // Erebos-Level (XP-System)
      (async function() {
        const levelEl = document.getElementById('erebos-level');
        if (!levelEl) return;

        // XP-Konfiguration
        const XP_PER_LEVEL = 100;
        const XP_ACTIONS = {
          'visit': 5,      // Seitenbesuch
          'wiki': 10,      // Wiki gelesen
          'forum': 10,     // Forum betreten
          'mail': 5,       // Mail geöffnet
          'chat': 10,      // Chat betreten
        };

        // XP vom Server laden (statt localStorage)
        let xp = 0;
        let tokens = 0;
        let achievements = [];
        try {
          const _addr = document.querySelector('.erebos-identity .addr')?.innerText || '';
          const resp = await fetch('/api/progress?identity_uuid=' + encodeURIComponent(_addr));
          if (resp.ok) {
            const data = await resp.json();
            xp = data.xp || 0;
            tokens = data.tokens || 0;
            achievements = data.achievements || [];
          }
        } catch (e) {}
        let level = Math.floor(xp / XP_PER_LEVEL) + 1;
        let lastVisit = parseInt(localStorage.getItem('erebos_last_visit') || '0', 10);
        const now = Date.now();

        // XP für Besuch (max. 1x pro Stunde)
        if (now - lastVisit > 3600000) {
          xp += XP_ACTIONS.visit;
          localStorage.setItem('erebos_last_visit', now.toString());
        }

        // XP für Seiten-spezifische Aktionen (max. 1x pro Seite pro Stunde)
        const path = location.pathname;
        const pageKey = 'erebos_xp_' + path;
        const lastPageVisit = parseInt(localStorage.getItem(pageKey) || '0', 10);
        if (now - lastPageVisit > 3600000) {
          if (path.includes('/wiki')) xp += XP_ACTIONS.wiki;
          else if (path.includes('/forum')) xp += XP_ACTIONS.forum;
          else if (path.includes('/mail')) xp += XP_ACTIONS.mail;
          else if (path.includes('/chat')) xp += XP_ACTIONS.chat;
          localStorage.setItem(pageKey, now.toString());
        }

        // Level berechnen
        const oldLevel = level;
        level = Math.floor(xp / XP_PER_LEVEL) + 1;
        // XP an den Server senden (statt localStorage)
        try {
          await fetch('/api/progress', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              identity_uuid: document.querySelector('.erebos-identity .addr')?.innerText || '',
              xp: xp, tokens: tokens, achievements: achievements
            })
          });
        } catch (e) {}

        // Widget aktualisieren
        const xpInLevel = xp % XP_PER_LEVEL;
        const xpPercent = Math.round((xpInLevel / XP_PER_LEVEL) * 100);
        levelEl.innerHTML = '<div>Level <span class="level-num">' + level + '</span></div>' +
          '<div class="xp-bar"><div class="xp-fill" style="width:' + xpPercent + '%"></div></div>' +
          '<div class="xp-text">' + xpInLevel + ' / ' + XP_PER_LEVEL + ' XP (' + xp + ' gesamt)</div>';

        // Level-Up-Toast
        if (level > oldLevel) {
          const toast = document.createElement('div');
          toast.className = 'achievement-toast show';
          toast.innerHTML = '<div class="title"><span class="icon">⭐</span>Level-Up!</div><div class="desc">Du bist jetzt Level ' + level + '!</div>';
          document.body.appendChild(toast);
          setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 600); }, 5000);
        }
      })();

      // Erebos-Token (Waehrung)
      (async function() {
        const tokenEl = document.getElementById('erebos-token-amount');
        if (!tokenEl) return;
        let tokens = 0;
        let xp = 0;
        let achievements = [];
        try {
          const resp = await fetch('/api/progress');
          if (resp.ok) {
            const data = await resp.json();
            tokens = data.tokens || 0;
            xp = data.xp || 0;
            achievements = data.achievements || [];
          }
        } catch (e) {}

        const TOKEN_ACTIONS = {
          'visit': 1,
          'wiki': 5,
          'forum': 5,
          'mail': 2,
          'chat': 5,
        };

        // Token werden bereits oben geladen (aus /api/progress)
        let lastVisit = parseInt(localStorage.getItem('erebos_tokens_last_visit') || '0', 10);
        const now = Date.now();

        // Token fuer Besuch (max. 1x pro Stunde)
        if (now - lastVisit > 3600000) {
          tokens += TOKEN_ACTIONS.visit;
          localStorage.setItem('erebos_tokens_last_visit', now.toString());
        }

        // Token fuer Seiten-spezifische Aktionen (max. 1x pro Seite pro Stunde)
        const path = location.pathname;
        const pageKey = 'erebos_tokens_' + path;
        const lastPageVisit = parseInt(localStorage.getItem(pageKey) || '0', 10);
        if (now - lastPageVisit > 3600000) {
          if (path.includes('/wiki')) tokens += TOKEN_ACTIONS.wiki;
          else if (path.includes('/forum')) tokens += TOKEN_ACTIONS.forum;
          else if (path.includes('/mail')) tokens += TOKEN_ACTIONS.mail;
          else if (path.includes('/chat')) tokens += TOKEN_ACTIONS.chat;
          localStorage.setItem(pageKey, now.toString());
        }

        // Token an den Server senden (statt localStorage)
        try {
          await fetch('/api/progress', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({xp: xp, tokens: tokens, achievements: achievements})
          });
        } catch (e) {}
        tokenEl.innerText = tokens;
      })();
      // Profil-Panel (Slide-in von rechts)
      (async function() {
        const panel = document.getElementById('profile-panel');
        const overlay = document.getElementById('profile-overlay');
        const closeBtn = document.getElementById('profile-close');
        if (!panel) return;

        function generateAvatar(addr) {
          const canvas = document.getElementById('profile-avatar');
          if (!canvas) return;
          const ctx = canvas.getContext('2d');
          const hash = addr.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
          ctx.fillStyle = '#1a0a0a';
          ctx.fillRect(0, 0, 100, 100);
          for (let i = 0; i < 16; i++) {
            const x = (hash * (i + 1) * 7) % 100;
            const y = (hash * (i + 1) * 13) % 100;
            const size = 8 + ((hash * (i + 1)) % 12);
            ctx.fillStyle = i % 2 === 0 ? '#ff3333' : '#ff6666';
            ctx.fillRect(x, y, size, size);
          }
          ctx.strokeStyle = '#ff3333';
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.arc(50, 50, 48, 0, Math.PI * 2);
          ctx.stroke();
        }

        function openPanel() {
          panel.classList.add('open');
          overlay.classList.add('open');
          const addr = document.querySelector('.erebos-identity .addr')?.innerText || '';
          document.getElementById('profile-addr').innerText = addr;
          document.getElementById('profile-handle').innerText = 'anon-' + addr.substring(0, 8);
          generateAvatar(addr);
          const xp = document.getElementById('profile-xp')?.innerText || '0';
          const tokens = localStorage.getItem('erebos_tokens') || '0';
          const level = Math.floor(parseInt(xp) / 100) + 1;
          document.getElementById('profile-level').innerText = level;
          document.getElementById('profile-xp').innerText = xp;
          document.getElementById('profile-tokens').innerText = tokens;
          const achievements = JSON.parse(localStorage.getItem('erebos_achievements') || '[]');
          const achList = document.getElementById('profile-achievements');
          if (achievements.length > 0) {
            const names = {
              'first_visit': '🌐 Willkommen in Erebos',
              'wiki_reader': '📖 Wissensdurstig',
              'forum_visitor': '💬 Teil der Community',
              'mail_checker': '📬 Postbote',
              'chat_joiner': '🗣️ Gesprächig'
            };
            achList.innerHTML = '<h3 style="color:#ff3333; margin-top:1em;">Erfolge</h3>' +
              achievements.map(a => '<div class="achievement-item"><div class="title">' + (names[a] || a) + '</div></div>').join('');
          }
        }

        function closePanel() {
          panel.classList.remove('open');
          overlay.classList.remove('open');
        }

        const identity = document.querySelector('.erebos-identity');
        if (identity) {
          identity.style.cursor = 'pointer';
          identity.addEventListener('click', function(e) {
            if (e.target.tagName === 'A' || e.target.classList.contains('sound-toggle')) return;
            openPanel();
          });
        }
        if (closeBtn) closeBtn.addEventListener('click', closePanel);
        if (overlay) overlay.addEventListener('click', closePanel);
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
      <div class="erebos-token"><span class="token-icon">🪙</span><span class="token-amount" id="erebos-token-amount">0</span> Token</div>
      <div class="links">
        <a href="/service">🛠️ Meine Services</a>
        <span class="sound-toggle" id="sound-toggle" title="Sound an/aus">🔊</span>
      </div>
    </div>
    <div class="erebos-time" id="erebos-time">Erebos-Zeit: ...</div>
    <div class="network-map">
      <div class="label">NETZWERK</div>
      <canvas id="network-canvas"></canvas>
    </div>
    <div class="erebos-level" id="erebos-level">
      <div>Level <span class="level-num">1</span></div>
      <div class="xp-bar"><div class="xp-fill" style="width:0%"></div></div>
      <div class="xp-text">0 / 100 XP</div>
    </div>
    <div class="profile-overlay" id="profile-overlay"></div>
    <div class="profile-panel" id="profile-panel">
      <button class="close-btn" id="profile-close">✕</button>
      <canvas class="avatar" id="profile-avatar" width="100" height="100"></canvas>
      <h2 id="profile-handle">anon-????</h2>
      <div class="addr-full" id="profile-addr"></div>
      <div class="stat-row"><span class="label">Level</span><span class="value" id="profile-level">1</span></div>
      <div class="stat-row"><span class="label">XP</span><span class="value" id="profile-xp">0</span></div>
      <div class="stat-row"><span class="label">Token</span><span class="value" id="profile-tokens">0</span></div>
      <div class="achievements-list" id="profile-achievements">
        <h3 style="color:#ff3333; margin-top:1em;">Erfolge</h3>
        <div style="color:#ff9999; font-size:0.8em;">Noch keine Erfolge.</div>
      </div>
      <a href="/service" class="panel-link">🛠️ Meine Services</a>
      <a href="/welcome" class="panel-link">🏠 Startseite</a>
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
