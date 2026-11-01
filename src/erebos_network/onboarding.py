"""Onboarding-Flow: Echter Verbindungsaufbau (Terminal) + Welcome-Seite."""

import logging

logger = logging.getLogger(__name__)


def render_onboard(anon_uuid, address, _page, _escape):
    """Detaillierter 30-Sekunden-Verbindungsaufbau mit Fortschrittsanzeige."""
    terminal_html = """
    <style>
      .terminal { background: #050508; color: #00ff88; font-family: 'Courier New', monospace; padding: 2em; border: 1px solid #00ff88; border-radius: 8px; max-width: 800px; margin: 2em auto; text-align: left; box-shadow: 0 0 20px rgba(0,255,136,0.2); }
      .log-line { margin: 0.8em 0; display: none; font-size: 0.9em; }
      .log-line.active { display: block; animation: fadeIn 0.3s; }
      .success { color: #00ff88; font-weight: bold; }
      .progress-container { margin-top: 2em; display: none; }
      .progress-container.active { display: block; }
      .progress-bar { width: 100%; height: 6px; background: #111; border-radius: 3px; overflow: hidden; margin-bottom: 0.5em; }
      .progress-fill { width: 0%; height: 100%; background: #00ff88; transition: width 0.4s ease; }
      .progress-text { text-align: right; font-size: 0.8em; color: #888; }
      @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    </style>
    <div class="terminal">
      <div id="logs"></div>
      <div class="progress-container" id="progress-container">
        <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
        <div class="progress-text" id="progress-text">0%</div>
      </div>
    </div>
    <script>
      const steps = [
        { msg: "> Initialisiere Erebos-Client (v0.4.2)...", delay: 2000 },
        { msg: "> Lade Post-Quanten-Kryptographie (ML-KEM-1024)...", delay: 3000 },
        { msg: "> Initialisiere liboqs und sichere Speicherbereiche...", delay: 2500 },
        { msg: "> Suche Rendezvous-Punkte im DHT...", delay: 4000 },
        { msg: "> Verbinde zu Peer 1 (Entry Node)...", delay: 2000 },
        { msg: "> Baue 3-Hop-Onion-Tunnel auf...", delay: 3000 },
        { msg: "> Führe X25519 Handshake durch...", delay: 2000 },
        { msg: "> Führe ML-KEM-1024 Handshake durch...", delay: 3000 },
        { msg: "> Verifiziere Peer-Signaturen (Ed25519)...", delay: 2500 },
        { msg: "> Generiere Identitaet & Schluesselpaar...", delay: 3000 },
        { msg: "> Registriere Identitaet im dezentralen Verzeichnis...", delay: 3000 },
        { msg: "> Richte anonymes Postfach ein...", delay: 2000 },
        { msg: "> Verbindung sicher aufgebaut. Leite weiter...", delay: 2000, final: true }
      ];

      const logsDiv = document.getElementById('logs');
      const progressContainer = document.getElementById('progress-container');
      const progressFill = document.getElementById('progress-fill');
      const progressText = document.getElementById('progress-text');
      
      let currentStep = 0;

      function runStep() {
        if (currentStep >= steps.length) return;

        const step = steps[currentStep];
        
        // Log-Zeile hinzufügen
        const line = document.createElement('div');
        line.className = 'log-line active' + (step.final ? ' success' : '');
        line.innerText = step.msg;
        logsDiv.appendChild(line);

        // Fortschritt aktualisieren
        if (currentStep > 0) {
          progressContainer.classList.add('active');
          const percent = Math.round((currentStep / (steps.length - 1)) * 100);
          progressFill.style.width = percent + '%';
          progressText.innerText = percent + '%';
        }

        // Nächster Schritt nach Delay
        currentStep++;
        if (step.final) {
          setTimeout(() => { window.location.href = '/welcome'; }, 1500);
        } else {
          setTimeout(runStep, step.delay);
        }
      }

      // Start
      setTimeout(runStep, 500);
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
