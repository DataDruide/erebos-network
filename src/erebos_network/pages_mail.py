"""Mail-Seiten: /mail/rotate (Bestaetigung + Ausfuehrung).

Enthaelt:
- _render_rotate_confirm(): Bestaetigungsseite fuer Key-Rotation
- _handle_rotate_post(): fuehrt die Rotation aus
"""

import logging

from . import forum
from .renderers import _page, _escape, _format_timestamp, _render_identity_box
from .forum_db import (
    load_mails, save_mail, mark_mail_read,
    get_or_create_mail_keys, get_mail_keys,
    get_mail_keys_by_version, set_mail_verified,
    rotate_mail_keys,
    check_rotate_rate_limit, record_rotate,
)
from .crypto.hybrid_kem import (
    encrypt_mail, decrypt_mail, sign_mail, verify_mail,
    verify_mail_with_status, VERIFIED, VERIFIED_OUTDATED,
    VERIFIED_EXPIRED, VERIFY_FAILED,
)

logger = logging.getLogger(__name__)


def _render_rotate_confirm(anon_uuid: str, address: str) -> bytes:
    """Bestaetigungsseite fuer Key-Rotation."""
    import time as _time
    import datetime as _dt

    keys = get_or_create_mail_keys(anon_uuid)
    if not keys:
        return _page(
            "Rotation", address,
            "<h1>Fehler</h1><p>Mail-Keys konnten nicht geladen werden.</p>"
            "<a class=\"btn\" href=\"/mail\">\u2190 Zur\u00fcck</a>",
        )

    version = keys.get("key_version") or 1
    valid_until = keys.get("valid_until")
    days_left = None
    until_str = "(unbekannt)"
    if valid_until:
        seconds_left = valid_until - _time.time()
        days_left = int(seconds_left / 86400)
        until_str = _dt.datetime.fromtimestamp(valid_until).strftime("%Y-%m-%d %H:%M")

    warning = ""
    if days_left is not None and days_left < 14:
        if days_left < 0:
            warning = (
                "<div style=\"background:#ffe0e0;border:1px solid #cc0000;"
                "padding:10px;margin:10px 0;\">"
                "<strong>\u26a0 Der aktuelle Schl\u00fcssel ist abgelaufen.</strong> "
                "Neue Mails werden als [Signatur abgelaufen] markiert.</div>"
            )
        else:
            warning = (
                "<div style=\"background:#fff4e0;border:1px solid #cc8800;"
                "padding:10px;margin:10px 0;\">"
                f"<strong>\u26a0 Der aktuelle Schl\u00fcssel l\u00e4uft in {days_left} Tagen ab.</strong></div>"
            )

    html = (
        "<h1>Schl\u00fcssel rotieren</h1>"
        "<div style=\"border:1px solid #ccc;padding:15px;margin:10px 0;background:#f9f9f9;\">"
        f"<p><strong>Aktuelle Version:</strong> v{version}</p>"
        f"<p><strong>G\u00fcltig bis:</strong> {until_str}</p>"
        f"{warning}"
        "</div>"
        "<div style=\"background:#fff8e0;border:1px solid #cc8800;padding:15px;margin:20px 0;\">"
        "<strong>Was passiert bei der Rotation?</strong>"
        "<ul>"
        f"<li>Ein neuer Schl\u00fcssel-Satz (v{version + 1}) wird generiert.</li>"
        f"<li>Der alte Schl\u00fcssel-Satz (v{version}) wird in der History als 'revoked' markiert.</li>"
        "<li>Alle zuk\u00fcnftigen Mails werden mit dem neuen Schl\u00fcssel signiert.</li>"
        "<li>Bereits gesendete Mails bleiben lesbar, werden aber als "
        "<strong>[Signatur veraltet]</strong> markiert.</li>"
        "<li>Diese Aktion kann <strong>nicht r\u00fcckg\u00e4ngig</strong> gemacht werden.</li>"
        "</ul>"
        "</div>"
        "<form method=\"POST\" action=\"/mail/rotate\" style=\"margin:20px 0;\">"
        "<button type=\"submit\" style=\"padding:10px 20px;font-size:16px;"
        "background:#cc3333;color:white;border:none;border-radius:4px;cursor:pointer;\">"
        "Ja, jetzt rotieren"
        "</button>"
        "</form>"
        "<a class=\"btn\" href=\"/mail\">\u2190 Abbrechen</a>"
    )

    return _page("Schl\u00fcssel rotieren", address, html)


def _handle_rotate_post(anon_uuid: str, address: str) -> bytes:
    """Fuehrt die Rotation aus. Bei Erfolg: Redirect zu /mail?rotated=1."""
    allowed, retry_after = check_rotate_rate_limit(anon_uuid)
    if not allowed:
        retry_sec = int(retry_after) + 1
        retry_min = int(retry_after / 60) + 1
        logger.warning(
            f"Rotation rate-limited: {anon_uuid[:8]} (retry in {retry_min} min)"
        )
        page = _page(
            "Rotation", address,
            f"<h1>Zu viele Rotationen</h1>"
            f"<p>Du hast deine Schl\u00fcssel zu oft rotiert. "
            f"Bitte warte noch <strong>{retry_min} Minuten</strong> "
            f"({retry_sec} Sekunden), bevor du erneut rotierst.</p>"
            "<a class=\"btn\" href=\"/mail\">\u2190 Zur\u00fcck</a>",
        )
        return b"RATE_LIMIT:" + str(retry_sec).encode() + b"\n" + page

    try:
        get_or_create_mail_keys(anon_uuid)
        new_keys = rotate_mail_keys(anon_uuid)
        record_rotate(anon_uuid)
        logger.info(
            f"Rotation erfolgreich: {anon_uuid[:8]} -> v{new_keys['key_version']}"
        )
        return b"REDIRECT:/mail?rotated=1"
    except ValueError as e:
        logger.warning(f"Rotation fehlgeschlagen: {e}")
        return _page(
            "Rotation", address,
            f"<h1>Rotation nicht m\u00f6glich</h1><p>{e}</p>"
            "<a class=\"btn\" href=\"/mail\">\u2190 Zur\u00fcck</a>",
        )
    except Exception as e:
        logger.error(f"Rotation unerwartet fehlgeschlagen: {e}")
        return _page(
            "Rotation", address,
            "<h1>Rotation fehlgeschlagen</h1>"
            "<p>Ein unerwarteter Fehler ist aufgetreten.</p>"
            "<a class=\"btn\" href=\"/mail\">\u2190 Zur\u00fcck</a>",
        )

def _render_mail(anon_uuid: str, address: str, query: str = "",
                 method: str = "GET", body: bytes = b"") -> bytes:
    """Rendert die /mail-Seite (Postfach + Formular + Key-Info).

    Wird von render_page aufgerufen, wenn path == "/mail".
    """
    short_id = anon_uuid[:8]


    if method == "POST":
        # Neue Mail speichern (hybrid PQ-verschluesselt)
        form = forum.parse_form_body(body)
        to_uuid = form.get("to_uuid", "").strip()
        subject = form.get("subject", "").strip()
        mail_body = form.get("body", "").strip()
        if to_uuid and subject and mail_body:
            # Empfaenger-Schluessel holen (oder generieren)
            recipient_keys = get_or_create_mail_keys(to_uuid)
            # Verschluesseln
            encrypted = encrypt_mail(
                recipient_x25519_pub=bytes.fromhex(recipient_keys["x25519_pub"]),
                recipient_mlkem_pub=bytes.fromhex(recipient_keys["mlkem_pub"]),
                plaintext=mail_body.encode("utf-8"),
            )
            # Signieren (eigener Ed25519 + ML-DSA-65)
            my_keys = get_or_create_mail_keys(anon_uuid)
            signatures = sign_mail(
                ed25519_priv=bytes.fromhex(my_keys["ed25519_priv"]),
                mldsa_priv=bytes.fromhex(my_keys["mldsa_priv"]),
                payload=mail_body.encode("utf-8"),
                mldsa_pub=bytes.fromhex(my_keys["mldsa_pub"]),
            )
            # Speichern
            save_mail(
                owner_uuid=to_uuid,
                sender_uuid=anon_uuid,
                subject=subject,
                body="",  # Klartext nicht speichern
                encrypted=True,
                encrypted_fields=encrypted,
                signatures=signatures,
                sender_verified=False,  # wird beim Empfaenger verifiziert
                sender_key_version=my_keys.get("key_version", 1),
                recipient_key_version=recipient_keys.get("key_version", 1),
            )
            logger.info(f"Mail von #{short_id} an #{to_uuid[:8]} PQ-verschluesselt gespeichert")
            return b"REDIRECT:/mail"
        return _page(
            "Mail", address,
            "<h1>Mail</h1><p>Alle Felder sind erforderlich.</p>"
            "<a class=\"btn\" href=\"/mail\">← Zurück</a>",
        )

    # GET: Mails anzeigen + Formular
    mails = load_mails(anon_uuid)
    # Eigene Schluessel laden oder generieren (fuer Entschluesselung
    # und Key-Info-Box). get_or_create ist idempotent und stellt
    # sicher, dass die UUID in mail_keys existiert.
    my_keys = get_or_create_mail_keys(anon_uuid)
    rows = ""
    for m in mails:
        unread = " <strong>[neu]</strong>" if not m["read"] else ""
        # Entschluesseln, falls verschluesselt
        if m.get("encrypted") and my_keys:
            try:
                # Empfaenger-Version aus der Mail
                r_version = m.get("recipient_key_version") or 1
                my_current_version = (my_keys or {}).get("key_version") or 1

                # Bei alter Empfaenger-Version: Privkeys aus History
                if r_version == my_current_version:
                    decrypt_keys = my_keys
                else:
                    decrypt_keys = get_mail_keys_by_version(
                        anon_uuid, r_version
                    )
                    if not decrypt_keys:
                        raise RuntimeError(
                            f"Keine Empfaenger-Key-Version v{r_version} "
                            f"fuer eigene UUID in History"
                        )

                plaintext = decrypt_mail(
                    recipient_x25519_priv=bytes.fromhex(decrypt_keys["x25519_priv"]),
                    recipient_mlkem_priv=bytes.fromhex(decrypt_keys["mlkem_priv"]),
                    encrypted={
                        "x25519_pub": m["x25519_pub"],
                        "mlkem_ct": m["mlkem_ct"],
                        "nonce": m["nonce"],
                        "ciphertext": m["ciphertext"],
                    },
                )
                # Signatur verifizieren
                sender_keys = get_mail_keys(m["sender_uuid"])
                # Rotation-bewusste Verifikation (3 Zustaende + Persistenz)
                persisted_status = m.get("sender_verified") or 0

                if persisted_status != 0:
                    # Status ist bereits in DB persistiert -> kein Re-Verify
                    verified = persisted_status
                else:
                    # Erster GET: Verify + persistieren
                    mail_key_version = m.get("sender_key_version") or 1
                    current_keys = sender_keys or {}
                    current_version = current_keys.get("key_version") or 1

                    if mail_key_version == current_version:
                        version_keys = current_keys
                    else:
                        version_keys = get_mail_keys_by_version(
                            m["sender_uuid"], mail_key_version
                        )

                    verified = VERIFY_FAILED  # Default
                    if version_keys and m.get("signature_ed25519"):
                        try:
                            mldsa_pub_hex = (version_keys.get("mldsa_pub")
                                             or m.get("signature_mldsa_pub") or "")
                            mldsa_pub_bytes = (bytes.fromhex(mldsa_pub_hex)
                                               if mldsa_pub_hex else None)
                            verified = verify_mail_with_status(
                                ed25519_pub=bytes.fromhex(version_keys["ed25519_pub"]),
                                payload=plaintext,
                                signatures={
                                    "ed25519": m["signature_ed25519"],
                                    "mldsa": m["signature_mldsa"],
                                    "mldsa_pub": mldsa_pub_hex,
                                },
                                mldsa_pub=mldsa_pub_bytes,
                                sender_key_version=mail_key_version,
                                sender_current_version=current_version,
                                valid_until=version_keys.get("valid_until"),
                            )
                        except Exception as e:
                            logger.warning(f"Signatur-Verifikation fehlgeschlagen: {e}")
                            verified = VERIFY_FAILED

                    # Persistieren als Zahl
                    status_map = {
                        VERIFIED: 1,
                        VERIFIED_OUTDATED: 2,
                        VERIFY_FAILED: 3,
                        VERIFIED_EXPIRED: 4,
                    }
                    status_num = status_map.get(verified, 3)
                    try:
                        set_mail_verified(m["id"], status_num)
                    except Exception as e:
                        logger.warning(f"sender_verified persistieren fehlgeschlagen: {e}")

                if verified == VERIFIED or verified == 1:
                    verified_badge = " <span style=\"color:green\">[verifiziert]</span>"
                elif verified == VERIFIED_OUTDATED or verified == 2:
                    verified_badge = (" <span style=\"color:orange\">"
                                      "[Signatur veraltet \u2014 Schluessel rotiert]</span>")
                elif verified == VERIFIED_EXPIRED or verified == 4:
                    verified_badge = (" <span style=\"color:orange\">"
                                      "[Signatur abgelaufen]</span>")
                else:
                    verified_badge = " <span style=\"color:red\">[nicht verifiziert]</span>"
                # Expiry-Hinweis (nur wenn valid_until vorhanden)
                expiry_hint = ""
                try:
                    valid_until = version_keys.get("valid_until")
                    if valid_until:
                        import time as _time
                        remaining_days = int((valid_until - _time.time()) / 86400)
                        if remaining_days < 0:
                            expiry_hint = ""
                        elif remaining_days == 0:
                            expiry_hint = " <small>[Key laeuft heute ab]</small>"
                        elif remaining_days <= 14:
                            expiry_hint = f" <small>[Key laeuft in {remaining_days} Tagen ab]</small>"
                except Exception:
                    pass
                body_html = _escape(plaintext.decode("utf-8", "replace")).replace("\n", "<br>") + verified_badge + expiry_hint
            except Exception as e:
                logger.error(f"Mail-Entschluesselung fehlgeschlagen: {e}")
                body_html = "<em>[Entschluesselung fehlgeschlagen]</em>"
        else:
            body_html = _escape(m["body"]).replace("\n", "<br>")
        rows += (
            f"<li><strong>{_escape(m['subject'])}</strong>{unread}<br>"
            f"<small>von #{_escape(m['sender_uuid'][:8])} · "
            f"{_format_timestamp(m['created_at'])}</small>"
            f"<p>{body_html}</p></li>\n"
        )
    if not rows:
        rows = "<li><em>Keine Mails.</em></li>"

    # Erfolgs-Banner bei ?rotated=1
    rotated_banner = ""
    if "rotated=1" in query:
        rotated_banner = (
            "<div style=\"background:#e0ffe0;border:1px solid #00aa00;"
            "padding:10px;margin:10px 0;border-radius:4px;\">"
            "<strong>✅ Schlüssel erfolgreich rotiert.</strong> "
            "Alte Mails werden jetzt als <em>[Signatur veraltet]</em> markiert."
            "</div>"
        )

    # Key-Info-Box mit Rotate-Button
    key_info = ""
    if my_keys:
        import time as _time
        import datetime as _dt
        version = my_keys.get("key_version") or 1
        valid_until = my_keys.get("valid_until")
        days_left = None
        until_str = "(unbekannt)"
        if valid_until:
            days_left = int((valid_until - _time.time()) / 86400)
            until_str = _dt.datetime.fromtimestamp(valid_until).strftime("%Y-%m-%d")
        warning = ""
        if days_left is not None and days_left < 14:
            if days_left < 0:
                warning = ' <span style="color:var(--danger);"><strong>⚠ Schlüssel abgelaufen</strong></span>'
            else:
                warning = f' <span style="color:var(--warn);"><strong>⚠ Läuft in {days_left} Tagen ab</strong></span>'
        key_info = (
            '<div class="key-status">'
            '<span class="dot"></span>'
            '<span>Schlüssel aktiv</span>'
            '</div>'
            '<div class="identity-row">'
            '<span class="identity-label">Aktuelle Version</span>'
            f'<span class="identity-value">v{version}</span>'
            '</div>'
            '<div class="identity-row">'
            '<span class="identity-label">Gültig bis</span>'
            f'<span class="identity-value">{until_str}{warning}</span>'
            '</div>'
            '<div style="margin-top:1rem;">'
            '<form method="GET" action="/mail/rotate">'
            '<button type="submit" class="rotate-btn" style="background:var(--warn);color:var(--bg);border:none;padding:.7rem 1.4rem;font-family:var(--mono);font-size:.9rem;font-weight:bold;border-radius:6px;cursor:pointer;">'
            'Schlüssel rotieren'
            '</button>'
            '</form>'
            '</div>'
        )

    # --- NEU: Moderne Mail-Seite mit Tabs, Live-Status, Copy-Buttons ---
    short_uuid = anon_uuid[:8]
    email = f"{short_uuid}@erebos"
    mails_count = len(mails)

    # Mails als JSON für JS
    import json as _json
    mails_json = _json.dumps([
        {
            "id": m.get("id"),
            "subject": m.get("subject", "(Kein Betreff)"),
            "sender": (m.get("sender_uuid") or "")[:8],
            "date": _format_timestamp(m.get("created_at", 0)),
            "read": bool(m.get("read")),
            "encrypted": bool(m.get("encrypted")),
        }
        for m in mails
    ], ensure_ascii=False)

    body_html = f"""
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Erebos Mail</title>
<style>
  :root {{
    --bg: #050508; --bg-card: #0d0d14; --bg-card-hover: #14141f;
    --fg: #c8d8c8; --fg-dim: #7a8a7a;
    --accent: #4ade80; --accent-dim: #22c55e33;
    --warn: #fbbf24; --danger: #f87171; --border: #1f2937;
    --mono: 'Courier New', 'Monaco', monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    background: var(--bg); color: var(--fg); font-family: var(--mono);
    font-size: 15px; line-height: 1.7; min-height: 100vh; padding: 2rem 1rem;
  }}
  body::before {{
    content: ''; position: fixed; inset: 0;
    background:
      radial-gradient(circle at 20% 20%, #4ade8010 0%, transparent 50%),
      radial-gradient(circle at 80% 80%, #4ade8008 0%, transparent 50%);
    pointer-events: none; z-index: -1;
  }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  header {{ text-align: center; margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--border); }}
  h1 {{ font-size: 2rem; color: var(--accent); letter-spacing: 2px; text-transform: uppercase; margin-bottom: .5rem; text-shadow: 0 0 20px var(--accent-dim); }}
  .subtitle {{ color: var(--fg-dim); font-size: .85rem; }}
  .tabs {{ display: flex; gap: .5rem; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: .5rem; flex-wrap: wrap; }}
  .tab {{ background: transparent; border: 1px solid var(--border); color: var(--fg-dim); padding: .5rem 1rem; font-family: var(--mono); font-size: .9rem; cursor: pointer; border-radius: 6px; transition: all .2s; }}
  .tab:hover {{ border-color: var(--accent); color: var(--fg); }}
  .tab.active {{ background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; animation: fadeIn .3s; }}
  @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: none; }} }}
  .card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; }}
  .card h2 {{ color: var(--accent); font-size: 1rem; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 1px; }}
  .identity-row {{ display: flex; justify-content: space-between; align-items: center; padding: .6rem 0; border-bottom: 1px solid var(--border); }}
  .identity-row:last-child {{ border-bottom: none; }}
  .identity-label {{ color: var(--fg-dim); font-size: .85rem; }}
  .identity-value {{ color: var(--fg); font-size: .85rem; font-family: var(--mono); word-break: break-all; text-align: right; max-width: 60%; }}
  .identity-value.muted {{ color: var(--fg-dim); font-style: italic; }}
  .copy-btn {{ background: var(--accent-dim); border: 1px solid var(--accent); color: var(--accent); padding: .2rem .6rem; margin-left: .5rem; border-radius: 4px; cursor: pointer; font-size: .75rem; font-family: var(--mono); transition: all .2s; }}
  .copy-btn:hover {{ background: var(--accent); color: var(--bg); }}
  form {{ display: flex; flex-direction: column; gap: 1rem; }}
  label {{ color: var(--fg-dim); font-size: .85rem; display: block; margin-bottom: .3rem; }}
  input, textarea {{ width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--fg); padding: .7rem 1rem; font-family: var(--mono); font-size: .9rem; border-radius: 6px; transition: border-color .2s; }}
  input:focus, textarea:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }}
  textarea {{ min-height: 120px; resize: vertical; }}
  button[type="submit"] {{ background: var(--accent); color: var(--bg); border: none; padding: .8rem 1.5rem; font-family: var(--mono); font-size: .95rem; font-weight: bold; border-radius: 6px; cursor: pointer; transition: all .2s; align-self: flex-start; }}
  button[type="submit"]:hover {{ background: #22c55e; }}
  button[type="submit"]:disabled {{ opacity: .5; cursor: not-allowed; }}
  .empty-state {{ text-align: center; padding: 3rem 1rem; color: var(--fg-dim); }}
  .empty-state .icon {{ font-size: 3rem; margin-bottom: 1rem; opacity: .5; }}
  .mail-item {{ background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; margin-bottom: .8rem; transition: border-color .2s; }}
  .mail-item:hover {{ border-color: var(--accent); }}
  .mail-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: .5rem; font-size: .85rem; }}
  .mail-from {{ color: var(--accent); }}
  .mail-date {{ color: var(--fg-dim); font-size: .75rem; }}
  .mail-subject {{ color: var(--fg); font-weight: bold; margin-bottom: .5rem; }}
  .mail-body {{ color: var(--fg-dim); font-size: .85rem; }}
  .key-status {{ display: flex; align-items: center; gap: .5rem; margin-bottom: 1rem; }}
  .key-status .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 8px var(--accent); animation: pulse 2s infinite; }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.4}} }}
  .footer {{ text-align: center; padding-top: 2rem; margin-top: 2rem; border-top: 1px solid var(--border); color: var(--fg-dim); font-size: .8rem; }}
  .footer a {{ color: var(--accent); text-decoration: none; border-bottom: 1px dashed var(--accent); }}
  .footer a:hover {{ border-bottom-style: solid; }}
  .instance {{ margin-top: .5rem; font-size: .75rem; word-break: break-all; }}
  .toast {{ position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%) translateY(100px); background: var(--accent); color: var(--bg); padding: .7rem 1.4rem; border-radius: 6px; font-weight: bold; font-size: .85rem; opacity: 0; transition: transform .3s, opacity .3s; pointer-events: none; z-index: 1000; }}
  .toast.show {{ transform: translateX(-50%) translateY(0); opacity: 1; }}
  .toast.error {{ background: var(--danger); color: #fff; }}
  .badge {{ display: inline-block; padding: .1rem .4rem; border-radius: 4px; font-size: .7rem; margin-left: .3rem; }}
  .badge-verified {{ background: #22c55e33; color: var(--accent); border: 1px solid var(--accent); }}
  .badge-outdated {{ background: #fbbf2433; color: var(--warn); border: 1px solid var(--warn); }}
  .badge-failed {{ background: #f8717133; color: var(--danger); border: 1px solid var(--danger); }}
  @media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }}
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Erebos Mail</h1>
    <p class="subtitle">Sichere Nachrichten im Erebos-Netzwerk</p>
  </header>

  {rotated_banner}

  <div class="tabs" role="tablist">
    <button class="tab active" data-tab="compose" role="tab">✉ Neue Mail</button>
    <button class="tab" data-tab="inbox" role="tab">📥 Postfach <span id="inbox-count">({mails_count})</span></button>
    <button class="tab" data-tab="identity" role="tab">🆔 Identität</button>
    <button class="tab" data-tab="keys" role="tab">🔑 Schlüssel</button>
  </div>

  <div class="panel active" id="panel-compose">
    <div class="card">
      <h2>Neue Mail senden</h2>
      <form method="post" action="/mail" id="compose-form">
        <div>
          <label for="to_uuid">An (UUID des Empfängers)</label>
          <input type="text" id="to_uuid" name="to_uuid" placeholder="z. B. 132aa4b3-74de-54e2-b5f5-525012af0264" required>
        </div>
        <div>
          <label for="subject">Betreff</label>
          <input type="text" id="subject" name="subject" maxlength="200" required>
        </div>
        <div>
          <label for="body">Nachricht</label>
          <textarea id="body" name="body" maxlength="4000" required></textarea>
        </div>
        <button type="submit" id="send-btn">Senden</button>
      </form>
    </div>
  </div>

  <div class="panel" id="panel-inbox">
    <div class="card">
      <h2>Deine Mails</h2>
      <div id="inbox-content">
        {_render_mail_list(anon_uuid)}
      </div>
    </div>
  </div>

  <div class="panel" id="panel-identity">
    <div class="card">
      <h2>Deine Identität</h2>
      <div class="identity-row">
        <span class="identity-label">UUID</span>
        <span class="identity-value" id="uuid-val">{anon_uuid} <button class="copy-btn" data-copy="{anon_uuid}">Kopieren</button></span>
      </div>
      <div class="identity-row">
        <span class="identity-label">E-Mail</span>
        <span class="identity-value">{email} <button class="copy-btn" data-copy="{email}">Kopieren</button></span>
      </div>
      <div class="identity-row">
        <span class="identity-label">Forum</span>
        <span class="identity-value muted">(wird beim ersten Forum-Login angelegt)</span>
      </div>
    </div>
  </div>

  <div class="panel" id="panel-keys">
    <div class="card">
      <h2>Schlüssel-Verwaltung</h2>
      {key_info}
    </div>
  </div>

  <footer class="footer">
    <a href="/">← Startseite</a>
    <div class="instance" id="instance"></div>
  </footer>
</div>

<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>
(() => {{
  'use strict';
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));

  const toast = $('#toast');
  let toastTimer;
  function showToast(msg, isError=false) {{
    toast.textContent = msg;
    toast.classList.toggle('error', isError);
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3000);
  }}

  // Tabs
  $$('.tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      $$('.tab').forEach(t => t.classList.remove('active'));
      $$('.panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const panel = $('#panel-' + tab.dataset.tab);
      if (panel) panel.classList.add('active');
    }});
  }});

  // Copy-Buttons
  $$('.copy-btn').forEach(btn => {{
    btn.addEventListener('click', async (e) => {{
      e.stopPropagation();
      try {{
        await navigator.clipboard.writeText(btn.dataset.copy);
        showToast('Kopiert!');
      }} catch {{
        showToast('Kopieren fehlgeschlagen', true);
      }}
    }});
  }});

  // Compose-Submit: Loading-State
  const form = $('#compose-form');
  if (form) {{
    form.addEventListener('submit', () => {{
      const btn = $('#send-btn');
      btn.disabled = true;
      btn.textContent = 'Sende…';
    }});
  }}

  // Rotate-Button
  const rotateBtn = document.querySelector('.rotate-btn');
  if (rotateBtn) {{
    rotateBtn.addEventListener('click', () => {{
      showToast('Schlüsselrotation würde jetzt starten (Demo)');
    }});
  }}

  // Instance
  const instance = $('#instance');
  if (instance) {{
    const host = window.location.hostname;
    instance.textContent = host && host !== 'localhost' && host !== '127.0.0.1'
      ? 'Diese Instanz: ' + host
      : 'Diese Instanz: lokaler Test-Modus';
  }}
}})();
</script>
</body>
</html>
"""
    return body_html.encode("utf-8")


def _render_mail_list(anon_uuid: str) -> str:
    """Lädt die Mails aus der DB und rendert sie im modernen Card-Style."""
    from .forum_db import load_mails
    mails = load_mails(anon_uuid)

    if not mails:
        return (
            '<div class="empty-state">'
            '<div class="icon">📭</div>'
            '<p>Dein Postfach ist leer.</p>'
            '<p style="font-size:.8rem;margin-top:.5rem;">'
            'Du hast noch keine Nachrichten empfangen.'
            '</p>'
            '</div>'
        )

    html = ""
    for m in mails:
        sender = (m.get("sender_uuid") or "Unbekannt")[:8]
        subject = m.get("subject", "(Kein Betreff)")
        body = (m.get("body") or "").replace("\n", "<br>")
        date = _format_timestamp(m.get("created_at", 0))
        unread = " <strong>[neu]</strong>" if not m.get("read") else ""

        html += (
            '<div class="mail-item">'
            '<div class="mail-header">'
            f'<span class="mail-from">Von: #{sender}</span>'
            f'<span class="mail-date">{date}</span>'
            '</div>'
            f'<div class="mail-subject">{_escape(subject)}{unread}</div>'
            f'<div class="mail-body">{body}</div>'
            '</div>'
        )
    return html



def _render_mail_modern(anon_uuid: str, address: str, query: str,
                        my_keys: dict, mails: list,
                        rotated_banner: str, key_info: str) -> str:
    """Moderne Mail-Seite mit Tabs, Live-Status, Copy-Buttons. Gibt str zurück."""
    short_uuid = anon_uuid[:8]
    email = f"{short_uuid}@erebos"
    mails_count = len(mails)
    mails_html = _render_mail_list(anon_uuid)

    body = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Erebos Mail</title>
<style>
  :root {{
    --bg: #050508; --bg-card: #0d0d14; --bg-card-hover: #14141f;
    --fg: #c8d8c8; --fg-dim: #7a8a7a;
    --accent: #4ade80; --accent-dim: #22c55e33;
    --warn: #fbbf24; --danger: #f87171; --border: #1f2937;
    --mono: 'Courier New', 'Monaco', monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    background: var(--bg); color: var(--fg); font-family: var(--mono);
    font-size: 15px; line-height: 1.7; min-height: 100vh; padding: 2rem 1rem;
  }}
  body::before {{
    content: ''; position: fixed; inset: 0;
    background:
      radial-gradient(circle at 20% 20%, #4ade8010 0%, transparent 50%),
      radial-gradient(circle at 80% 80%, #4ade8008 0%, transparent 50%);
    pointer-events: none; z-index: -1;
  }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  header {{ text-align: center; margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--border); }}
  h1 {{ font-size: 2rem; color: var(--accent); letter-spacing: 2px; text-transform: uppercase; margin-bottom: .5rem; text-shadow: 0 0 20px var(--accent-dim); }}
  .subtitle {{ color: var(--fg-dim); font-size: .85rem; }}
  .tabs {{ display: flex; gap: .5rem; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: .5rem; flex-wrap: wrap; }}
  .tab {{ background: transparent; border: 1px solid var(--border); color: var(--fg-dim); padding: .5rem 1rem; font-family: var(--mono); font-size: .9rem; cursor: pointer; border-radius: 6px; transition: all .2s; }}
  .tab:hover {{ border-color: var(--accent); color: var(--fg); }}
  .tab.active {{ background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; animation: fadeIn .3s; }}
  @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: none; }} }}
  .card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; }}
  .card h2 {{ color: var(--accent); font-size: 1rem; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 1px; }}
  .identity-row {{ display: flex; justify-content: space-between; align-items: center; padding: .6rem 0; border-bottom: 1px solid var(--border); }}
  .identity-row:last-child {{ border-bottom: none; }}
  .identity-label {{ color: var(--fg-dim); font-size: .85rem; }}
  .identity-value {{ color: var(--fg); font-size: .85rem; font-family: var(--mono); word-break: break-all; text-align: right; max-width: 60%; }}
  .identity-value.muted {{ color: var(--fg-dim); font-style: italic; }}
  .copy-btn {{ background: var(--accent-dim); border: 1px solid var(--accent); color: var(--accent); padding: .2rem .6rem; margin-left: .5rem; border-radius: 4px; cursor: pointer; font-size: .75rem; font-family: var(--mono); transition: all .2s; }}
  .copy-btn:hover {{ background: var(--accent); color: var(--bg); }}
  form {{ display: flex; flex-direction: column; gap: 1rem; }}
  label {{ color: var(--fg-dim); font-size: .85rem; display: block; margin-bottom: .3rem; }}
  input, textarea {{ width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--fg); padding: .7rem 1rem; font-family: var(--mono); font-size: .9rem; border-radius: 6px; transition: border-color .2s; }}
  input:focus, textarea:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }}
  textarea {{ min-height: 120px; resize: vertical; }}
  button[type="submit"] {{ background: var(--accent); color: var(--bg); border: none; padding: .8rem 1.5rem; font-family: var(--mono); font-size: .95rem; font-weight: bold; border-radius: 6px; cursor: pointer; transition: all .2s; align-self: flex-start; }}
  button[type="submit"]:hover {{ background: #22c55e; }}
  button[type="submit"]:disabled {{ opacity: .5; cursor: not-allowed; }}
  .empty-state {{ text-align: center; padding: 3rem 1rem; color: var(--fg-dim); }}
  .empty-state .icon {{ font-size: 3rem; margin-bottom: 1rem; opacity: .5; }}
  .mail-item {{ background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; margin-bottom: .8rem; transition: border-color .2s; }}
  .mail-item:hover {{ border-color: var(--accent); }}
  .mail-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: .5rem; font-size: .85rem; }}
  .mail-from {{ color: var(--accent); }}
  .mail-date {{ color: var(--fg-dim); font-size: .75rem; }}
  .mail-subject {{ color: var(--fg); font-weight: bold; margin-bottom: .5rem; }}
  .mail-body {{ color: var(--fg-dim); font-size: .85rem; }}
  .key-status {{ display: flex; align-items: center; gap: .5rem; margin-bottom: 1rem; }}
  .key-status .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 8px var(--accent); animation: pulse 2s infinite; }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.4}} }}
  .footer {{ text-align: center; padding-top: 2rem; margin-top: 2rem; border-top: 1px solid var(--border); color: var(--fg-dim); font-size: .8rem; }}
  .footer a {{ color: var(--accent); text-decoration: none; border-bottom: 1px dashed var(--accent); }}
  .footer a:hover {{ border-bottom-style: solid; }}
  .instance {{ margin-top: .5rem; font-size: .75rem; word-break: break-all; }}
  .toast {{ position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%) translateY(100px); background: var(--accent); color: var(--bg); padding: .7rem 1.4rem; border-radius: 6px; font-weight: bold; font-size: .85rem; opacity: 0; transition: transform .3s, opacity .3s; pointer-events: none; z-index: 1000; }}
  .toast.show {{ transform: translateX(-50%) translateY(0); opacity: 1; }}
  .toast.error {{ background: var(--danger); color: #fff; }}
  @media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }}
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Erebos Mail</h1>
    <p class="subtitle">Sichere Nachrichten im Erebos-Netzwerk</p>
  </header>

  {rotated_banner}

  <div class="tabs" role="tablist">
    <button class="tab active" data-tab="compose" role="tab">✉ Neue Mail</button>
    <button class="tab" data-tab="inbox" role="tab">📥 Postfach <span id="inbox-count">({mails_count})</span></button>
    <button class="tab" data-tab="identity" role="tab">🆔 Identität</button>
    <button class="tab" data-tab="keys" role="tab">🔑 Schlüssel</button>
  </div>

  <div class="panel active" id="panel-compose">
    <div class="card">
      <h2>Neue Mail senden</h2>
      <form method="post" action="/mail" id="compose-form">
        <div>
          <label for="to_uuid">An (UUID des Empfängers)</label>
          <input type="text" id="to_uuid" name="to_uuid" placeholder="z. B. 132aa4b3-74de-54e2-b5f5-525012af0264" required>
        </div>
        <div>
          <label for="subject">Betreff</label>
          <input type="text" id="subject" name="subject" maxlength="200" required>
        </div>
        <div>
          <label for="body">Nachricht</label>
          <textarea id="body" name="body" maxlength="4000" required></textarea>
        </div>
        <button type="submit" id="send-btn">Senden</button>
      </form>
    </div>
  </div>

  <div class="panel" id="panel-inbox">
    <div class="card">
      <h2>Deine Mails</h2>
      <div id="inbox-content">
        {mails_html}
      </div>
    </div>
  </div>

  <div class="panel" id="panel-identity">
    <div class="card">
      <h2>Deine Identität</h2>
      <div class="identity-row">
        <span class="identity-label">UUID</span>
        <span class="identity-value">{anon_uuid} <button class="copy-btn" data-copy="{anon_uuid}">Kopieren</button></span>
      </div>
      <div class="identity-row">
        <span class="identity-label">E-Mail</span>
        <span class="identity-value">{email} <button class="copy-btn" data-copy="{email}">Kopieren</button></span>
      </div>
      <div class="identity-row">
        <span class="identity-label">Forum</span>
        <span class="identity-value muted">(wird beim ersten Forum-Login angelegt)</span>
      </div>
    </div>
  </div>

  <div class="panel" id="panel-keys">
    <div class="card">
      <h2>Schlüssel-Verwaltung</h2>
      {key_info}
    </div>
  </div>

  <footer class="footer">
    <a href="/">← Startseite</a>
    <div class="instance" id="instance"></div>
  </footer>
</div>

<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>
(() => {{
  'use strict';
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));

  const toast = $('#toast');
  let toastTimer;
  function showToast(msg, isError=false) {{
    toast.textContent = msg;
    toast.classList.toggle('error', isError);
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3000);
  }}

  $$('.tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      $$('.tab').forEach(t => t.classList.remove('active'));
      $$('.panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const panel = $('#panel-' + tab.dataset.tab);
      if (panel) panel.classList.add('active');
    }});
  }});

  $$('.copy-btn').forEach(btn => {{
    btn.addEventListener('click', async (e) => {{
      e.stopPropagation();
      try {{
        await navigator.clipboard.writeText(btn.dataset.copy);
        showToast('Kopiert!');
      }} catch {{
        showToast('Kopieren fehlgeschlagen', true);
      }}
    }});
  }});

  const form = $('#compose-form');
  if (form) {{
    form.addEventListener('submit', () => {{
      const btn = $('#send-btn');
      btn.disabled = true;
      btn.textContent = 'Sende…';
    }});
  }}

  const instance = $('#instance');
  if (instance) {{
    const host = window.location.hostname;
    instance.textContent = host && host !== 'localhost' && host !== '127.0.0.1'
      ? 'Diese Instanz: ' + host
      : 'Diese Instanz: lokaler Test-Modus';
  }}
}})();
</script>
</body>
</html>"""
    return body
