"""Dreistufiger Human Validator (Hash, Puzzle, Emotion)."""

def render_human_challenge(address: str, stage: int, hash_code: str = "", error: str = "") -> bytes:
    if stage == 1:
        content = f"""
        <h2>Ebene 1: Terminal-Befehl</h2>
        <p>Kopiere diesen Hash und füge ihn im Feld unten ein:</p>
        <div style="background:#000; color:#00ff41; padding:1em; font-family:monospace; font-size:1.2em; letter-spacing:0.2em; border:1px solid #00ff41;">
            {hash_code}
        </div>
        <form method="POST" action="/human/verify" style="margin-top:2em;">
            <input type="hidden" name="stage" value="1">
            <input type="hidden" name="expected" value="{hash_code}">
            <p><label>Hash eingeben:<br>
            <input type="text" name="input_code" required style="width:100%; padding:0.5em; background:#161b22; border:1px solid #30363d; color:#00ff41; font-family:monospace;"></label></p>
            <button type="submit" class="btn" style="background:#00ff41; color:#000; padding:0.8em 1.5em; font-weight:bold;">Bestätigen</button>
        </form>
        """
    elif stage == 2:
        content = """
        <h2>Ebene 2: Das Puzzle</h2>
        <p>Ordne die Teile richtig an. (Tipp: Das Lösungswort ist der Name des Netzwerks).</p>
        <div style="display:flex; gap:10px; justify-content:center; margin:2em 0;">
            <div style="background:#00ff41; color:#000; padding:1em; font-weight:bold; border-radius:4px;">B</div>
            <div style="background:#00ff41; color:#000; padding:1em; font-weight:bold; border-radius:4px;">O</div>
            <div style="background:#00ff41; color:#000; padding:1em; font-weight:bold; border-radius:4px;">S</div>
            <div style="background:#00ff41; color:#000; padding:1em; font-weight:bold; border-radius:4px;">E</div>
            <div style="background:#00ff41; color:#000; padding:1em; font-weight:bold; border-radius:4px;">R</div>
            <div style="background:#00ff41; color:#000; padding:1em; font-weight:bold; border-radius:4px;">E</div>
        </div>
        <form method="POST" action="/human/verify">
            <input type="hidden" name="stage" value="2">
            <p><label>Lösungswort:<br>
            <input type="text" name="input_code" required style="width:100%; padding:0.5em; background:#161b22; border:1px solid #30363d; color:#00ff41;"></label></p>
            <button type="submit" class="btn" style="background:#00ff41; color:#000; padding:0.8em 1.5em; font-weight:bold;">Prüfen</button>
        </form>
        """
    elif stage == 3:
        content = """
        <h2>Ebene 3: Emotionale Logik</h2>
        <p>Welches dieser Gefühle passt <strong>nicht</strong> zu den anderen?</p>
        <ul style="list-style:none; padding:0; font-size:1.2em; line-height:2;">
            <li>Freude</li>
            <li>Glück</li>
            <li>Zufriedenheit</li>
            <li>Angst</li>
        </ul>
        <form method="POST" action="/human/verify">
            <input type="hidden" name="stage" value="3">
            <p><label>Das unpassende Gefühl:<br>
            <input type="text" name="input_code" required style="width:100%; padding:0.5em; background:#161b22; border:1px solid #30363d; color:#00ff41;"></label></p>
            <button type="submit" class="btn" style="background:#00ff41; color:#000; padding:0.8em 1.5em; font-weight:bold;">Auflösen</button>
        </form>
        """
    else:
        return b"Fehler: Unbekannte Stufe"

    html = f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>Human Validation - Erebos</title></head>
<body style="background:#0d1117; color:#c9d1d9; font-family:sans-serif; display:flex; justify-content:center; align-items:center; min-height:100vh;">
  <div style="background:#161b22; border:1px solid #30363d; padding:3em; border-radius:12px; max-width:500px; width:100%;">
    <h1 style="color:#00ff41; font-family:monospace; text-align:center;">EREBOS HUMAN VALIDATION</h1>
    <p style="color:#8b949e; text-align:center;">Beweise, dass du ein Mensch bist (Ebene {stage}/3)</p>
    {f'<p style="color:#ff4060; text-align:center;">{error}</p>' if error else ''}
    <hr style="border-color:#30363d; margin:2em 0;">
    {content}
  </div>
</body>
</html>"""
    return html.encode("utf-8")
