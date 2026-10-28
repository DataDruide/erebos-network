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
    """Willkommens-Seite: UUID, E-Mail, Forum-Username, Warnung."""
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
        '<img src="/avatar.jpg" alt="Avatar" class="avatar" style="width:100px; height:100px; border-radius:50%; border:3px solid #00ff88; ">'
        '<h1 style="font-family:monospace; color:#00ff88; margin-top:1em;">WILLKOMMEN BEI EREBOS</h1>'
        '</header>'
        '<div style="border:1px solid #00ff88; padding:2em; margin:1.5em 0; background:rgba(0,255,136,0.05); border-radius:12px; backdrop-filter: blur(10px); box-shadow: 0 8px 32px rgba(0,0,0,0.3);">'
        '<p style="color:#00ff88; font-size:0.9em; letter-spacing:0.15em; margin-bottom:1em;">DEINE IDENTITAET</p>'
        '<p style="margin:0.8em 0;"><strong>UUID:</strong><br>'
        '<code style="color:#00ff88; word-break:break-all;">' + _escape(anon_uuid) + '</code></p>'
        '<p style="margin:0.8em 0;"><strong>E-Mail:</strong><br>'
        '<code style="color:#00ff88;">' + _escape(email) + '</code></p>'
        '<p style="margin:0.8em 0;"><strong>Forum:</strong><br>'
        '<code style="color:#00ff88;">' + _escape(forum_username) + '</code></p>'
        '</div>'
        '<div style="border:1px solid #ff8800; padding:1.5em; margin:1.5em 0; background:rgba(255,136,0,0.05); border-radius:12px; box-shadow: 0 8px 32px rgba(0,0,0,0.3);">'
        '<p style="color:#ff8800; font-size:1em; letter-spacing:0.1em; margin-bottom:0.8em;">WICHTIG - SCHREIB DAS AUF</p>'
        '<p style="color:#ffcc88; margin:0.5em 0; line-height:1.6;">'
        'Diese Daten werden <strong>nicht dauerhaft</strong> gespeichert. '
        'Nach einem Browser-Neustart sind sie <strong>verloren</strong>. '
        'Notiere UUID und E-Mail-Adresse jetzt.'
        '</p>'
        '</div>'
        '<form method="POST" action="/welcome/ack" style="margin:2em 0;">'
        '<button type="submit" class="btn" style="background:#00ff88; color:#000; font-weight:bold; padding:1em 2em; border:1px solid #00ff88; border-radius:4px; cursor:pointer; transition: background-color 0.2s, color 0.2s;">'
        'Ich habe es aufgeschrieben'
        '</button>'
        '</form>'
        '<p style="text-align:center; margin-top:1em;">'
        '<a class="btn" href="/mail" style="color:#00ff88; margin-right:1em; text-decoration:none; border:1px solid #00ff88; padding:0.5em 1em; border-radius:4px; display:inline-block;">-> Zum Postfach</a> '
        '<a class="btn" href="/forum" style="color:#00ff88;">-> Zum Forum</a>'
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
