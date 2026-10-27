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
                warning = " <span style=\"color:#cc0000;\"><strong>⚠ Schlüssel abgelaufen</strong></span>"
            else:
                warning = f" <span style=\"color:#cc8800;\"><strong>⚠ Läuft in {days_left} Tagen ab</strong></span>"
        key_info = (
            "<hr style=\"margin:20px 0;\">"
            "<div style=\"background:#f0f0f0;padding:10px;border-radius:4px;\">"
            "<strong>Schlüssel-Verwaltung</strong><br>"
            f"Aktuelle Version: <strong>v{version}</strong> "
            f"(gültig bis {until_str}){warning}<br>"
            "<form method=\"GET\" action=\"/mail/rotate\" style=\"margin-top:10px;\">"
            "<button type=\"submit\" class=\"btn\">Schlüssel rotieren</button>"
            "</form>"
            "</div>"
        )

    body_html = (
        f"<h1>Mail</h1>\n"
        f"{rotated_banner}"
        f"{_render_identity_box(anon_uuid)}"
        "<h2>Neue Mail senden</h2>\n"
        "<form method=\"post\" action=\"/mail\">\n"
        "  <p><label>An (UUID des Empfaengers):<br>"
        "  <input name=\"to_uuid\" required style=\"width:100%\" "
        "placeholder=\"z.B. 132aa4b3-74de-54e2-b5f5-525012af0264\"></label></p>\n"
        "  <p><label>Betreff:<br>"
        "  <input name=\"subject\" required maxlength=\"200\" style=\"width:100%\"></label></p>\n"
        "  <p><label>Nachricht:<br>"
        "  <textarea name=\"body\" rows=\"6\" maxlength=\"4000\" required style=\"width:100%\"></textarea></label></p>\n"
        "  <p><button type=\"submit\" class=\"btn\">Senden</button></p>\n"
        "</form>\n"
        "<h2>Deine Mails</h2>\n"
        f"<ul>\n{rows}\n</ul>\n"
        f"{key_info}"
        "<a class=\"btn\" href=\"/\">← Startseite</a>\n"
    )
    return _page("MAIL", address, body_html, hero_image="mail-bg.jpeg")
