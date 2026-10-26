"""HTML-Seiten fuer den Erebos Hidden-Service (Startseite + Wiki)."""

import json
import logging
from pathlib import Path
from typing import Optional

from . import forum
from .forum_db import (load_mails, save_mail, mark_mail_read,
                       get_or_create_mail_keys, get_mail_keys,
                       get_mail_keys_by_version)
from .crypto.hybrid_kem import (encrypt_mail, decrypt_mail, sign_mail, verify_mail,
                                verify_mail_with_status, VERIFIED, VERIFIED_OUTDATED,
                                VERIFY_FAILED)

logger = logging.getLogger(__name__)

WIKI_PATH = Path("/app/wiki.json")


def parse_request_path(request: bytes) -> str:
    """Liest den Pfad aus der ersten HTTP-Zeile (z.B. 'GET /wiki HTTP/1.1')."""
    if not request:
        return "/"
    first_line = request.split(b"\r\n", 1)[0].decode("utf-8", "replace")
    parts = first_line.split(" ")
    if len(parts) < 2:
        return "/"
    target = parts[1]
    # Query-String abschneiden
    return target.split("?", 1)[0] or "/"


def _load_wiki_entries() -> list:
    """Laedt die Wiki-Eintraege aus /app/wiki.json (oder gibt [] zurueck)."""
    try:
        if WIKI_PATH.exists():
            data = json.loads(WIKI_PATH.read_text(encoding="utf-8"))
            return data.get("entries", [])
    except Exception as e:
        logger.warning(f"Wiki-JSON konnte nicht geladen werden: {e}")
    return []


def _format_timestamp(ts: float) -> str:
    """Formatiert einen Unix-Timestamp als lesbares Datum."""
    import time as _time
    try:
        return _time.strftime("%Y-%m-%d %H:%M", _time.localtime(ts))
    except Exception:
        return "?"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _page(title: str, address: str, body: str) -> bytes:
    html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"de\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        f"  <title>{_escape(title)}</title>\n"
        "  <style>\n"
        "    body { font-family: sans-serif; max-width: 720px; margin: 2em auto; padding: 1em; line-height: 1.6; }\n"
        "    code { background: #f0f0f0; padding: 0.2em 0.4em; }\n"
        "    h1 { color: #2c3e50; }\n"
        "    h2 { color: #34495e; margin-top: 1.5em; }\n"
        "    ul { padding-left: 1.4em; }\n"
        "    .btn { display: inline-block; margin-top: 1em; padding: 0.6em 1.2em; background: #2c3e50; color: #fff; text-decoration: none; border-radius: 4px; }\n"
        "    .btn:hover { background: #1a252f; }\n"
        "    .addr { font-size: 0.85em; color: #666; word-break: break-all; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        f"<p class=\"addr\"><strong>Diese Instanz:</strong> <code>{_escape(address)}</code></p>\n"
        "</body>\n"
        "</html>\n"
    )
    return html.encode("utf-8")


def render_welcome(address: str, client_id: str, request_line: str) -> bytes:
    """Anonyme Begruessungsseite: UUID, Dienste, Status auf einen Blick."""
    import hashlib as _hashlib
    import uuid as _uuid

    # Anonyme UUID aus client_id ableiten (deterministisch, nicht rueckfuehrbar)
    if client_id:
        # uuid5 mit fester Namespace -> deterministisch, aber ohne client_id
        # nicht reproduzierbar. Die UUID ist NICHT die client_id.
        anon_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))
    else:
        anon_uuid = str(_uuid.uuid4())

    short_id = anon_uuid[:8]

    body = (
        "<h1>Willkommen im Erebos-Netzwerk</h1>\n"
        "<p>Du bist anonym verbunden. Diese Seite zeigt dir alles auf einen Blick.</p>\n"
        "<h2>Deine anonyme Kennung</h2>\n"
        f"<p><code>{_escape(anon_uuid)}</code></p>\n"
        f"<p><small>Kurz-ID: <strong>#{_escape(short_id)}</strong> · "
        "Diese Kennung ist nur fuer diese Verbindung gueltig und nicht "
        "rueckfuehrbar auf deine IP oder Person.</small></p>\n"
        "<h2>Verbindung</h2>\n"
        "<ul>\n"
        "  <li><strong>Status:</strong> Verbunden ueber Erebos-Netzwerk</li>\n"
        "  <li><strong>Verschluesselung:</strong> Ende-zu-Ende (X25519 + ML-KEM-1024 + ChaCha20-Poly1305)</li>\n"
        "  <li><strong>Routing:</strong> 3-Hop-Onion (Proxy &rarr; peer2 &rarr; peer3 &rarr; peer1 &rarr; Hidden Service)</li>\n"
        "  <li><strong>Deine IP:</strong> fuer den Hidden Service nicht sichtbar</li>\n"
        "</ul>\n"
        "<h2>Verfuegbare Dienste</h2>\n"
        "<ul>\n"
        "  <li><a href=\"/mail\"><strong>Mail</strong></a> — anonyme Nachrichten (UUID-basiert)</li>\n"
        "  <li><a href=\"/wiki\"><strong>Hidden Wiki</strong></a> — Verzeichnis der Dienste</li>\n"
        "  <li><a href=\"/forum\"><strong>Erebos Community</strong></a> — Forum mit Threads und Antworten</li>\n"
        "  <li><a href=\"/regeln\"><strong>Regeln</strong></a> — was hier erlaubt ist und was nicht</li>\n"
        "  <li><a href=\"/forum/health\"><strong>Health</strong></a> — Status des Dienstes</li>\n"
        "</ul>\n"
        "<h2>Deine Rechte</h2>\n"
        "<ul>\n"
        "  <li>Kein Login, kein Passwort, keine E-Mail-Adresse noetig.</li>\n"
        "  <li>Keine personenbezogenen Daten werden gespeichert.</li>\n"
        "  <li>Deine IP ist fuer den Hidden Service nicht sichtbar.</li>\n"
        "  <li>Der Inhalt deiner Anfragen ist Ende-zu-Ende verschluesselt.</li>\n"
        "</ul>\n"
        f"<p><em>Deine Anfrage:</em> <code>{_escape(request_line)}</code></p>\n"
        f"<p><small>Hidden-Service-Adresse: <code>{_escape(address)}</code></small></p>\n"
        "<a class=\"btn\" href=\"/wiki\">Zur Hidden Wiki &rarr;</a>\n"
        "<a class=\"btn\" href=\"/forum\">Zum Forum &rarr;</a>\n"
        "<a class=\"btn\" href=\"/regeln\">Zu den Regeln &rarr;</a>\n"
    )
    return _page("Willkommen bei Erebos", address, body)


def render_landing(address: str, request_line: str) -> bytes:
    body = (
        "<h1>Willkommen im Erebos-Netzwerk</h1>\n"
        "<p>Du hast einen Hidden Service über das Erebos-Netzwerk erreicht.</p>\n"
        "<h2>Regeln</h2>\n"
        "<ul>\n"
        "  <li><strong>Respekt:</strong> Keine Angriffe auf andere Dienste, keine Belästigung.</li>\n"
        "  <li><strong>Keine illegalen Inhalte:</strong> Keine CSAM, keine Gewaltverherrlichung, keine Drogen-/Waffenhandels-Plattformen.</li>\n"
        "  <li><strong>Privatsphäre:</strong> Keine Deanonymisierungsversuche, keine Datensammlung über andere Nutzer.</li>\n"
        "  <li><strong>Kein Spam:</strong> Keine Massenwerbung, keine Flooding-Angriffe.</li>\n"
        "  <li><strong>Forschungsprototyp:</strong> Dies ist ein Experiment, keine Produktionsinfrastruktur. Keine Garantie auf Verfügbarkeit oder Anonymität.</li>\n"
        "</ul>\n"
        f"<p><em>Deine Anfrage:</em> <code>{_escape(request_line)}</code></p>\n"
        "<a class=\"btn\" href=\"/wiki\">Zur Hidden Wiki →</a>\n"
    )
    return _page("Willkommen bei Erebos", address, body)


def render_wiki(address: str) -> bytes:
    entries = _load_wiki_entries()
    items = []
    for e in entries:
        name = _escape(str(e.get("name", "?")))
        url = _escape(str(e.get("url", "#")))
        desc = _escape(str(e.get("desc", "")))
        items.append(
            f"<li><a href=\"{url}\">{name}</a> — {desc}<br><code>{url}</code></li>"
        )
    if not items:
        items.append("<li><em>Noch keine Einträge. Bearbeite wiki.json und mounte sie neu.</em></li>")
    body = (
        "<h1>Hidden Wiki</h1>\n"
        "<p>Eine Liste von Diensten im Erebos-Netzwerk. Platzhalter-Einträge, bis echte Dienste existieren.</p>\n"
        f"<ul>\n{chr(10).join(items)}\n</ul>\n"
        "<a class=\"btn\" href=\"/\">← Zurück zur Startseite</a>\n"
    )
    return _page("Hidden Wiki", address, body)


def render_page(path: str, address: str, request_line: str, method: str = "GET",
                body: bytes = b"", query: str = "", client_id: str = "",
                username: str = "", session_token: str = "",
                admin_cookie: str = "") -> bytes:
    admin_token_value = ""
    if query:
        from urllib.parse import parse_qs
        q = parse_qs(query)
        admin_token_value = (q.get("admin", [""])[0] or "")
    # Admin: Cookie (bevorzugt) ODER Token in URL (Fallback)
    admin = (
        forum.is_admin_cookie(admin_cookie, client_id=client_id)
        or forum.is_admin(admin_token_value)
    )

    if path == "/":
        return render_welcome(address, client_id, request_line)
    if path == "/regeln":
        return render_landing(address, request_line)
    if path == "/wiki":
        return render_wiki(address)
    if path == "/mail":
        # Anonyme UUID aus client_id ableiten (wie auf der Startseite)
        import uuid as _uuid
        if client_id:
            anon_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))
        else:
            anon_uuid = str(_uuid.uuid4())
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
        # Eigene Schluessel laden (fuer Entschluesselung)
        my_keys = get_mail_keys(anon_uuid)
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
                    # Rotation-bewusste Verifikation (3 Zustaende)
                    mail_key_version = m.get("sender_key_version") or 1
                    current_keys = sender_keys or {}
                    current_version = current_keys.get("key_version") or 1

                    if mail_key_version == current_version:
                        version_keys = current_keys
                    else:
                        version_keys = get_mail_keys_by_version(
                            m["sender_uuid"], mail_key_version
                        )

                    verified = False  # Fallback fuer alte Logik
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
                            )
                        except Exception as e:
                            logger.warning(f"Signatur-Verifikation fehlgeschlagen: {e}")
                            verified = VERIFY_FAILED

                    if verified == VERIFIED:
                        verified_badge = " <span style=\"color:green\">[verifiziert]</span>"
                    elif verified == VERIFIED_OUTDATED:
                        verified_badge = (" <span style=\"color:orange\">"
                                          "[Signatur veraltet \u2014 Schluessel rotiert]</span>")
                    else:
                        verified_badge = " <span style=\"color:red\">[nicht verifiziert]</span>"
                    body_html = _escape(plaintext.decode("utf-8", "replace")).replace("\n", "<br>") + verified_badge
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

        body_html = (
            f"<h1>Mail</h1>\n"
            f"<p>Deine anonyme Adresse: <code>{_escape(anon_uuid)}</code> "
            f"(Kurz-ID: <strong>#{_escape(short_id)}</strong>)</p>\n"
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
            "<a class=\"btn\" href=\"/\">← Startseite</a>\n"
        )
        return _page("Mail", address, body_html)

    if path == "/forum":
        return _page("Erebos Community", address, forum.render_categories(client_id=client_id, username=username, admin=admin, admin_token=""))
    if path == "/forum/admin/login":
        # Setzt das Admin-Cookie. Token kommt aus ?admin=<token>.
        if not admin_token_value:
            return _page(
                "Nicht erlaubt", address,
                "<h1>Nicht erlaubt</h1><p>Token fehlt.</p>",
            )
        if not forum.is_admin(admin_token_value):
            return _page(
                "Nicht erlaubt", address,
                "<h1>Nicht erlaubt</h1><p>Token ungueltig.</p>",
            )
        cookie_value = forum.admin_login(admin_token_value)
        forum._store_admin_session(cookie_value, client_id=client_id)
        return (
            b"REDIRECT:/forum\nSET_ADMIN:"
            + cookie_value.encode("utf-8")
        )

    if path == "/forum/admin":
        if not admin:
            return _page(
                "Nicht erlaubt",
                address,
                "<h1>Nicht erlaubt</h1>"
                "<p>Admin-Token fehlt oder ist falsch.</p>"
                "<a class=\"btn\" href=\"/forum\">← Zurück</a>",
            )
        return _page("Admin", address, forum.render_admin_status(client_id=client_id, admin_token=admin_token_value))

    if path == "/forum/admin/authors":
        if not admin:
            return _page(
                "Nicht erlaubt", address,
                "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
            )
        return _page("Autoren", address, forum.render_admin_authors())

    if path == "/forum/admin/authors/delete" and method == "POST":
        if not admin:
            return _page(
                "Nicht erlaubt", address,
                "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
            )
        form = forum.parse_form_body(body)
        author = form.get("author", "")
        result = forum.delete_posts_by_author(author)
        logger.info(f"Admin: {author} -> {result}")
        return b"REDIRECT:/forum/admin/authors?admin=" + admin_token_value.encode("utf-8")
    if path == "/forum/search":
        from urllib.parse import parse_qs as _pq
        q = ""
        if query:
            q = (_pq(query).get("q", [""])[0] or "")
        results = forum.search_threads(q)
        return _page(f"Suche: {q}", address, forum.render_search_results(q, results))

    # /forum/<category>?page=N&sort=X (aber nicht /forum/neu, /forum/search, /forum/admin*, /forum/<id>)
    if (path.startswith("/forum/")
            and not path.startswith("/forum/neu")
            and not path.startswith("/forum/search")
            and not path.startswith("/forum/admin")
            and "/" not in path[len("/forum/"):]):
        cat_slug = path[len("/forum/"):]
        # Nur als Kategorie behandeln, wenn sie existiert
        if forum.get_category(cat_slug) is not None:
            from urllib.parse import parse_qs as _pq
            params = _pq(query) if query else {}
            page_n = 1
            sort = "active"
            try:
                page_n = int(params.get("page", ["1"])[0])
            except (ValueError, TypeError):
                page_n = 1
            sort = params.get("sort", ["active"])[0] or "active"
            return _page(
                forum.get_category(cat_slug)["name"],
                address,
                forum.render_thread_list(
                    cat_slug, page=page_n, sort=sort,
                    admin=admin, client_id=client_id,
                ),
            )

    # --- Auth-Routen ---
    if path == "/forum/login":
        if method == "POST":
            form = forum.parse_form_body(body)
            token, reason = forum.login_user(
                form.get("username", ""), form.get("password", ""),
                client_id=client_id,
            )
            if token:
                return b"REDIRECT:/forum\nSET_SESSION:" + token.encode("utf-8")
            if reason == "rate_limit":
                # HTTP 429: Too Many Requests
                return b"RATE_LIMIT:1"
            return _page("Login", address, forum.render_login_form(
                "Login fehlgeschlagen."
            ))
        return _page("Login", address, forum.render_login_form())

    if path == "/forum/register":
        if method == "POST":
            form = forum.parse_form_body(body)
            ok, msg = forum.register_user(form.get("username", ""), form.get("password", ""))
            if ok:
                return b"REDIRECT:/forum/login"
            return _page("Registrieren", address, forum.render_register_form(msg))
        return _page("Registrieren", address, forum.render_register_form())

    if path == "/forum/logout":
        forum.logout_user(session_token)
        return b"REDIRECT:/forum\nCLEAR_SESSION:1"

    if path == "/forum/my-threads":
        if not username:
            return b"REDIRECT:/forum/login"
        return _page("Meine Threads", address, forum.render_my_threads(username))

    # --- Admin: Reports + Mod-Log ---
    if path == "/forum/admin/reports":
        if not admin:
            return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
        return _page("Meldungen", address, forum.render_reports())

    if path.startswith("/forum/admin/reports/") and path.endswith("/resolve") and method == "POST":
        if not admin:
            return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
        idx_str = path[len("/forum/admin/reports/"):-len("/resolve")]
        try:
            idx = int(idx_str)
        except ValueError:
            idx = -1
        forum.resolve_report(idx)
        return b"REDIRECT:/forum/admin/reports?admin=" + admin_token_value.encode("utf-8")

    if path == "/forum/admin/modlog":
        if not admin:
            return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
        return _page("Mod-Log", address, forum.render_mod_log())

    if path == "/forum/health":
        return _page("Health", address, forum.render_health())

    # --- Report posten ---
    if "/post/" in path and path.endswith("/quote"):
        head = path[: -len("/quote")]
        parts = head.split("/post/")
        if len(parts) == 2:
            tid = parts[0].replace("/forum/", "")
            try:
                idx = int(parts[1])
            except ValueError:
                idx = -1
            t = forum.find_thread(tid)
            if t is None:
                return _page("Nicht gefunden", address, forum.render_not_found())
            return _page("Zitat", address, forum.render_quote_form(t, idx))

    if "/post/" in path and path.endswith("/report"):
        if method == "POST":
            head = path[: -len("/report")]
            parts = head.split("/post/")
            if len(parts) == 2:
                tid = parts[0].replace("/forum/", "")
                try:
                    idx = int(parts[1])
                except ValueError:
                    idx = -1
                form = forum.parse_form_body(body)
                forum.report_post(tid, idx, form.get("reason", ""), username or "Anonym")
                return b"REDIRECT:/forum/" + tid.encode("utf-8")
        # GET: Formular
        head = path[: -len("/report")]
        parts = head.split("/post/")
        if len(parts) == 2:
            tid = parts[0].replace("/forum/", "")
            try:
                idx = int(parts[1])
            except ValueError:
                idx = -1
            return _page("Melden", address, forum.render_report_form(tid, idx))

    # --- Admin: Bans ---
    if path == "/forum/admin/bans":
        if not admin:
            return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
        return _page("Ban-Liste", address, forum.render_bans())

    if path == "/forum/admin/ban" and method == "POST":
        if not admin:
            return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
        form = forum.parse_form_body(body)
        username = form.get("username", "")
        reason = form.get("reason", "")
        forum.ban_user(username, reason)
        forum.log_moderation("ban", username, "admin")
        return b"REDIRECT:/forum/admin/bans?admin=" + admin_token_value.encode("utf-8")

    if path.startswith("/forum/admin/bans/") and path.endswith("/unban") and method == "POST":
        if not admin:
            return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
        idx_str = path[len("/forum/admin/bans/"):-len("/unban")]
        try:
            idx = int(idx_str)
        except ValueError:
            idx = -1
        forum.unban_user(idx)
        forum.log_moderation("unban", f"index {idx}", "admin")
        return b"REDIRECT:/forum/admin/bans?admin=" + admin_token_value.encode("utf-8")

    # --- Sticky/Locked-Toggles ---
    if path.startswith("/forum/") and path.endswith("/toggle/sticky") and method == "POST":
        if not admin:
            return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
        tid = path[len("/forum/"):-len("/toggle/sticky")]
        forum.toggle_sticky(tid)
        forum.log_moderation("sticky", tid, "admin")
        return b"REDIRECT:/forum/" + tid.encode("utf-8")

    if path.startswith("/forum/") and path.endswith("/toggle/locked") and method == "POST":
        if not admin:
            return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
        tid = path[len("/forum/"):-len("/toggle/locked")]
        forum.toggle_locked(tid)
        forum.log_moderation("locked", tid, "admin")
        return b"REDIRECT:/forum/" + tid.encode("utf-8")

    if path == "/forum/neu":
        if method == "POST":
            form = forum.parse_form_body(body)
            tid = forum.create_thread(
                form.get("title", ""),
                form.get("author", ""),
                form.get("body", ""),
                client_id=client_id,
                category_id=form.get("category_id", "allgemein"),
            )
            if tid:
                return b"REDIRECT:" + f"/forum/{tid}".encode("utf-8")
            return _page(
                "Fehler",
                address,
                "<p>Thread konnte nicht erstellt werden "
                "(Titel und Beitrag erforderlich).</p>"
                + forum.render_new_thread_form(),
            )
        from urllib.parse import parse_qs as _pq
        cat_pre = "allgemein"
        if query:
            cat_pre = (_pq(query).get("category", ["allgemein"])[0] or "allgemein")
        return _page(
            "Neuer Thread", address,
            forum.render_new_thread_form(category_id=cat_pre),
        )
    if path.startswith("/forum/"):
        rest = path[len("/forum/"):]

        if rest.endswith("/antwort"):
            tid = rest[: -len("/antwort")]
            form = forum.parse_form_body(body)
            ok = forum.add_reply(tid, form.get("author", ""), form.get("body", ""), client_id=client_id)
            if not ok:
                return _page(
                    "Rate-Limit",
                    address,
                    forum.render_rate_limited(),
                )
            return b"REDIRECT:" + f"/forum/{tid}".encode("utf-8")

        if rest.endswith("/delete") and method == "POST":
            if not admin:
                return _page(
                    "Nicht erlaubt",
                    address,
                    "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
                )
            tid = rest[: -len("/delete")]
            forum.delete_thread(tid)
            return b"REDIRECT:/forum"

        # /forum/<id>/post/<idx>/delete
        if "/post/" in rest and rest.endswith("/delete") and method == "POST":
            if not admin:
                return _page(
                    "Nicht erlaubt",
                    address,
                    "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
                )
            head = rest[: -len("/delete")]
            tid, idx_str = head.split("/post/", 1)
            try:
                idx = int(idx_str)
            except ValueError:
                idx = -1
            forum.delete_post(tid, idx)
            return b"REDIRECT:" + f"/forum/{tid}".encode("utf-8")

        # /forum/<id>/post/<idx>/edit
        if "/post/" in rest and rest.endswith("/edit"):
            if not admin:
                return _page(
                    "Nicht erlaubt", address,
                    "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
                )
            head = rest[: -len("/edit")]
            tid, idx_str = head.split("/post/", 1)
            try:
                idx = int(idx_str)
            except ValueError:
                idx = -1
            t = forum.find_thread(tid)
            if t is None:
                return _page("Nicht gefunden", address, forum.render_not_found())
            if method == "POST":
                form = forum.parse_form_body(body)
                forum.edit_post(tid, idx, form.get("body", ""))
                return b"REDIRECT:" + f"/forum/{tid}".encode("utf-8")
            return _page("Bearbeiten", address, forum.render_edit_form(t, idx))

        t = forum.find_thread(rest)
        if t is None:
            return _page("Nicht gefunden", address, forum.render_not_found())
        return _page(t["title"], address, forum.render_thread(t, admin=admin))
    return _page(
        "404 Nicht gefunden",
        address,
        "<h1>404 — Nicht gefunden</h1><p>Diese Seite existiert nicht.</p>"
        "<a class=\"btn\" href=\"/\">Zur Startseite</a>",
    )


def http_response(status: int, content_type: str, body: bytes,
                  location: str = "", set_cookie: str = "") -> bytes:
    reason = {200: "OK", 302: "Found", 403: "Forbidden", 404: "Not Found",
              413: "Payload Too Large", 429: "Too Many Requests",
              500: "Internal Server Error"}.get(status, "OK")
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
    )
    if location:
        headers += f"Location: {location}\r\n"
    if set_cookie:
        headers += f"Set-Cookie: {set_cookie}\r\n"
    # Security Headers (OWASP A05:2025 Security Misconfiguration)
    headers += (
        "X-Content-Type-Options: nosniff\r\n"
        "X-Frame-Options: DENY\r\n"
        "Referrer-Policy: no-referrer\r\n"
        "Permissions-Policy: geolocation=(), microphone=(), camera=()\r\n"
        # CSP: kein externes Script, kein Inline-Script, nur eigene Styles
        # und Inline-Styles (die Templates nutzen style="...")
        "Content-Security-Policy: default-src 'self'; "
        "script-src 'none'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "form-action 'self'; "
        "frame-ancestors 'none'\r\n"
    )
    headers += "Connection: close\r\n\r\n"
    return headers.encode("ascii") + body


def parse_http_request(data: bytes) -> tuple:
    """Parst einen rohen HTTP-Request.

    Returns:
        (method, path, headers_dict, body_bytes)
    """
    if not data:
        return ("GET", "/", {}, b"")
    if b"\r\n\r\n" in data:
        head, body = data.split(b"\r\n\r\n", 1)
    else:
        head, body = data, b""
    lines = head.split(b"\r\n")
    if not lines:
        return ("GET", "/", {}, b"")
    request_line = lines[0].decode("utf-8", "replace")
    parts = request_line.split(" ")
    method = parts[0] if parts else "GET"
    target = parts[1] if len(parts) > 1 else "/"
    path = target.split("?", 1)[0] or "/"
    headers = {}
    for line in lines[1:]:
        if b":" in line:
            k, v = line.split(b":", 1)
            headers[k.decode("ascii", "replace").strip().lower()] = v.decode(
                "utf-8", "replace"
            ).strip()
    return (method, path, headers, body)
