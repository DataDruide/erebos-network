"""HTML-Seiten fuer den Erebos Hidden-Service (Startseite + Wiki)."""

import json
import logging
from pathlib import Path
from typing import Optional

from . import forum
from .onboarding import render_onboard, render_welcome_onboarded, render_recover
from .pages_onboarding import render_welcome, render_landing, render_wiki
from .pages_services import render_services_list, render_service_error, render_upload_form
from . import service_manager as _services
from .renderers import _page, _escape, _format_timestamp, _render_identity_box
from .http_utils import http_response, parse_http_request
from .pages_mail import _render_rotate_confirm, _handle_rotate_post, _render_mail
from .pages_forum import (
    render_forum_index, render_forum_health,
    render_forum_login, render_forum_register,
    render_forum_logout,
    render_forum_admin_login, render_forum_admin_dashboard,
    render_forum_admin_authors, render_forum_admin_authors_delete,
    render_forum_admin_mods, render_forum_admin_mods_set,
    render_forum_admin_reports, render_forum_admin_reports_resolve,
    render_forum_admin_modlog, render_forum_admin_bans,
    render_forum_admin_ban, render_forum_admin_bans_unban,
    render_forum_admin_promote,
    render_forum_search, render_forum_my_threads, render_forum_new_thread,
    render_forum_toggle_sticky, render_forum_toggle_locked,
    render_forum_category, render_forum_thread,
)
from .forum_db import (find_identity_by_identifier, get_or_create_forum_session, load_mails, save_mail, mark_mail_read,
                       get_or_create_mail_keys, get_mail_keys,
                       get_mail_keys_by_version, set_mail_verified,
                       rotate_mail_keys,
                       check_rotate_rate_limit, record_rotate,
                       create_identity, get_identity,
    get_user_role,
)
from .crypto.hybrid_kem import (encrypt_mail, decrypt_mail, sign_mail, verify_mail,
                                verify_mail_with_status, VERIFIED, VERIFIED_OUTDATED,
                                VERIFIED_EXPIRED, VERIFY_FAILED)

logger = logging.getLogger(__name__)



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


def render_page(path: str, address: str, request_line: str, method: str = "GET",
                body: bytes = b"", query: str = "", client_id: str = "",
                username: str = "", session_token: str = "",
                admin_cookie: str = "", identity_uuid: str = "",
                mod: bool = False, headers: dict = None) -> bytes:
    if headers is None:
        headers = {}
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
    # users.role: neue Admin-Rolle (wenn eingeloggt)
    mod = admin  # mod ist mindestens admin
    if username:
        try:
            role = get_user_role(username)
            if role == "admin":
                admin = True
                mod = True
            elif role == "mod":
                mod = True
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Chat-Routen (eigener Hidden Service, Port 8081)
    # -----------------------------------------------------------------
    if path in ("/chat", "/chat/"):
        from . import pages_chat
        return pages_chat.render_start(address).encode("utf-8")

    if path == "/chat/random" and method == "GET":
        from . import chat as _chat, pages_chat
        result = _chat.random_match(client_id)
        if "matched" in result:
            return f"REDIRECT:/chat/room/{result['matched']}".encode()
        return pages_chat.render_random_waiting(address).encode("utf-8")

    if path == "/chat/random/status" and method == "GET":
        from . import chat as _chat
        import json as _json
        return b"JSON:" + _json.dumps(_chat.random_status(client_id)).encode()

    if path == "/chat/create" and method == "POST":
        from . import chat as _chat
        room_id = _chat.create_room()
        _chat.join_room(room_id, client_id)
        return f"REDIRECT:/chat/room/{room_id}".encode()

    if path == "/chat/join" and method == "POST":
        from . import chat as _chat, pages_chat
        from urllib.parse import parse_qs
        q = parse_qs(body.decode("utf-8", errors="replace"))
        room_id = (q.get("room_id", [""])[0] or "").strip()
        if not _chat.room_exists(room_id):
            return pages_chat.render_error(
                address, f"Raum {room_id or '(leer)'} existiert nicht."
            ).encode("utf-8")
        _chat.join_room(room_id, client_id)
        return f"REDIRECT:/chat/room/{room_id}".encode()

    # === SERVICE-BEREICH ===
    if path.startswith("/service/") and path.endswith("/upload"):
        name = path[len("/service/"):-len("/upload")]
        if method == "GET":
            files = _services.list_files(name)
            return render_upload_form(address, name, files)
        # POST: multipart/form-data
        ct = ""
        for h in str(headers).split(";"):
            pass
        # Content-Type aus den Headern lesen
        # (headers ist ein dict, das von der Runtime übergeben wird)
        try:
            content_type = headers.get("content-type", "") if isinstance(headers, dict) else ""
        except Exception:
            content_type = ""
        # Multipart parsen
        import re as _re
        m = _re.search(r"boundary=([^;]+)", content_type)
        if not m:
            return render_service_error(address, "Ungültiger Content-Type (multipart erwartet)")
        boundary = m.group(1).strip('"').encode()
        parts = body.split(b"--" + boundary)
        filename = None
        content = b""
        for part in parts:
            if not part.strip() or part.strip() == b"--":
                continue
            if b"\r\n\r\n" not in part:
                continue
            part_headers, part_content = part.split(b"\r\n\r\n", 1)
            part_content = part_content.rstrip(b"\r\n")
            cd = _re.search(rb'name="([^"]+)"(?:; filename="([^"]+)")?', part_headers)
            if not cd:
                continue
            if cd.group(2):
                filename = cd.group(2).decode("utf-8", "replace")
                content = part_content
                break
        if not filename:
            return render_service_error(address, "Keine Datei im Upload gefunden")
        result = _services.upload_file(name, filename, content)
        if not result["ok"]:
            return render_service_error(address, result["message"])
        return b"REDIRECT:/service"

    if path == "/service":
        services = _services.list_services()
        return render_services_list(address, services)

    # Datei-Upload
    if path == "/service/create" and method == "POST":
        from urllib.parse import parse_qs
        q = parse_qs(body.decode("utf-8", errors="replace"))
        name = (q.get("name", [""])[0] or "").strip()
        port_str = (q.get("port", ["0"])[0] or "0").strip()
        pages = (q.get("pages", [""])[0] or "").strip()
        try:
            port = int(port_str)
        except ValueError:
            return render_service_error(address, "Ungültiger Port")
        if not name or not pages:
            return render_service_error(address, "Name und Verzeichnis erforderlich")
        if not (8083 <= port <= 8099):
            return render_service_error(address, "Port muss zwischen 8083 und 8099 liegen")
        result = _services.create_service(name, port, pages)
        if not result["ok"]:
            return render_service_error(address, result["message"])
        return b"REDIRECT:/service"

    if path.startswith("/service/") and path.endswith("/stop") and method == "POST":
        name = path[len("/service/"):-len("/stop")]
        result = _services.stop_service(name)
        if not result["ok"]:
            return render_service_error(address, result["message"])
        return b"REDIRECT:/service"

    if path.startswith("/service/") and path.endswith("/delete") and method == "POST":
        name = path[len("/service/"):-len("/delete")]
        result = _services.delete_service(name, delete_key=True)
        if not result["ok"]:
            return render_service_error(address, result["message"])
        return b"REDIRECT:/service"

    if path.startswith("/chat/room/") and "/e2e/" in path:
        from . import chat_e2e as _e2e
        import json as _json
        parts = path.split("/")
        # /chat/room/<id>/e2e/<action>  -> parts = ['', 'chat', 'room', '<id>', 'e2e', '<action>']
        if len(parts) < 6:
            return _json.dumps({"error": "invalid_e2e_url"}).encode()
        room_id = parts[3]
        action = parts[5]

        if action == "key" and method == "POST":
            body_json = _json.loads(body.decode("utf-8") or "{}")
            role = body_json.get("role", "")
            x_pub_hex = body_json.get("x25519_pub", "")
            mlkem_pub_hex = body_json.get("mlkem_pub", "")
            mlkem_ct_hex = body_json.get("mlkem_ct", "") or ""

            if role not in ("initiator", "responder"):
                return b"JSON:" + _json.dumps({"error": "invalid_role"}).encode()
            if not x_pub_hex or not mlkem_pub_hex:
                return b"JSON:" + _json.dumps({"error": "missing_pubkey"}).encode()

            try:
                x_pub = bytes.fromhex(x_pub_hex)
                mlkem_pub = bytes.fromhex(mlkem_pub_hex)
                mlkem_ct = bytes.fromhex(mlkem_ct_hex) if mlkem_ct_hex else b""
            except ValueError:
                return b"JSON:" + _json.dumps({"error": "invalid_hex"}).encode()

            payload = _e2e.E2EPayload(
                role=role,
                x25519_pub=x_pub,
                mlkem_pub=mlkem_pub,
                mlkem_ct=mlkem_ct,
            )
            _e2e.store_key(room_id, client_id, role, payload)
            return b"JSON:" + _json.dumps({"ok": True}).encode()

        if action == "key" and method == "GET":
            my_key = _e2e.get_key(room_id, client_id)
            if not my_key:
                return b"JSON:" + _json.dumps({"error": "no_own_key"}).encode()
            partner = _e2e.get_partner_key(room_id, client_id, my_key["role"])
            if partner is None:
                return b"JSON:" + _json.dumps({"waiting": True}).encode()
            return b"JSON:" + _json.dumps({
                "role": partner["role"],
                "x25519_pub": partner["x25519_pub"].hex(),
                "mlkem_pub": partner["mlkem_pub"].hex(),
                "mlkem_ct": partner["mlkem_ct"].hex() if partner["mlkem_ct"] else "",
            }).encode()

        if action == "send" and method == "POST":
            body_json = _json.loads(body.decode("utf-8") or "{}")
            nonce_hex = body_json.get("nonce", "")
            ct_hex = body_json.get("ciphertext", "")
            key_epoch = body_json.get("key_epoch", 0)
            if not nonce_hex or not ct_hex:
                return b"JSON:" + _json.dumps({"error": "missing_fields"}).encode()
            try:
                nonce = bytes.fromhex(nonce_hex)
                ct = bytes.fromhex(ct_hex)
            except ValueError:
                return b"JSON:" + _json.dumps({"error": "invalid_hex"}).encode()
            msg_id = _e2e.store_encrypted_message(room_id, client_id, nonce, ct, key_epoch)
            return b"JSON:" + _json.dumps({"ok": True, "id": msg_id}).encode()

        if action == "messages" and method == "GET":
            from urllib.parse import parse_qs
            q = parse_qs(query)
            try:
                since = float((q.get("since", ["0"])[0] or "0"))
            except ValueError:
                since = 0.0
            msgs = _e2e.get_encrypted_messages(room_id, since)
            return b"JSON:" + _json.dumps([
                {
                    "id": m["id"],
                    "from": m["from"],
                    "nonce": m["nonce"].hex(),
                    "ciphertext": m["ciphertext"].hex(),
                    "key_epoch": m.get("key_epoch", 0),
                    "ts": m["ts"],
                }
                for m in msgs
            ]).encode()

        return b"JSON:" + _json.dumps({"error": "unknown_e2e_action"}).encode()

    if path.startswith("/chat/room/"):
        from . import chat as _chat, pages_chat
        parts = path.split("/")
        # ['', 'chat', 'room', '<id>', ...]
        if len(parts) < 4:
            return pages_chat.render_error(address, "Ungueltige Raum-URL.").encode("utf-8")
        room_id = parts[3]
        if not _chat.room_exists(room_id):
            return pages_chat.render_error(
                address, f"Raum {room_id} existiert nicht."
            ).encode("utf-8")

        if len(parts) == 4 and method == "GET":
            _chat.join_room(room_id, client_id)
            return pages_chat.render_room(room_id, address, client_id).encode("utf-8")

        if len(parts) == 5 and parts[4] == "messages" and method == "GET":
            from urllib.parse import parse_qs
            q = parse_qs(query)
            try:
                since = float((q.get("since", ["0"])[0] or "0"))
            except ValueError:
                since = 0.0
            msgs = _chat.get_messages(room_id, since)
            import json as _json
            return b"JSON:" + _json.dumps(msgs).encode()

        if len(parts) == 5 and parts[4] == "send" and method == "POST":
            from urllib.parse import parse_qs
            q = parse_qs(body.decode("utf-8", errors="replace"))
            msg = (q.get("message", [""])[0] or "").strip()
            ok, reason = _chat.send_message(room_id, client_id, msg)
            if not ok and reason.startswith("rate_limit:"):
                retry = reason.split(":", 1)[1]
                html = (
                    "<!DOCTYPE html><html><body>"
                    "<h1>429 - Zu viele Nachrichten</h1>"
                    f"<p>Bitte warte {retry} Sekunden.</p>"
                    "<p><a href=\"/chat/room/" + room_id + "\">Zurueck</a></p>"
                    "</body></html>"
                ).encode("utf-8")
                return b"RATE_LIMIT:" + retry.encode() + b"\n" + html
            return f"REDIRECT:/chat/room/{room_id}".encode()

        return pages_chat.render_error(address, "Unbekannte Chat-Aktion.").encode("utf-8")

    if path == "/":
        # Onboarding: wenn Client existiert, aber noch keine Identity
        # -> automatisch zu /onboard
        import uuid as _uuid
        if client_id:
            anon_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))
            ident = get_identity(anon_uuid)
            if ident is None or ident.get("onboarded_at") is None:
                return b"REDIRECT:/onboard"
        return render_welcome(address, client_id, request_line)
    if path == "/regeln":
        return render_landing(address, request_line)
    if path == "/wiki":
        return render_wiki(address)
    if path == "/mail/rotate":
        # UUID: identity_uuid bevorzugt, sonst aus client_id ableiten
        import uuid as _uuid
        if identity_uuid:
            anon_uuid = identity_uuid
        elif client_id:
            anon_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))
        else:
            return _page(
                "Rotation", address,
                "<h1>Fehler</h1><p>Keine Session. Bitte besuche zuerst <a href=\"/mail\">/mail</a>.</p>",
            )
        if method == "POST":
            return _handle_rotate_post(anon_uuid, address)
        return _render_rotate_confirm(anon_uuid, address)

    if path == "/recover":
        if method == "POST":
            form = forum.parse_form_body(body)
            identifier = (form.get("identifier", "") or "").strip()
            if not identifier:
                return render_recover(
                    address, _page, _escape,
                    error="Bitte UUID oder E-Mail eingeben.",
                )
            ident = find_identity_by_identifier(identifier)
            if ident is None:
                return render_recover(
                    address, _page, _escape,
                    error="Keine Identitaet mit dieser UUID/E-Mail gefunden.",
                )
            logger.info(f"Recovery: Identitaet {ident['uuid'][:8]} wiederhergestellt")
            return (
                b"REDIRECT:/mail\n"
                + b"SET_IDENTITY:" + ident["uuid"].encode() + b"\n"
                + b"CLEAR_SESSION:1"
            )
        return render_recover(address, _page, _escape)

    if path == "/onboard":
        import uuid as _uuid
        if identity_uuid:
            anon_uuid = identity_uuid
        elif client_id:
            anon_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))
        else:
            return _page(
                "Onboarding", address,
                "<h1>Onboarding</h1><p>Keine Session. Bitte lade die Seite neu.</p>",
            )
        return render_onboard(anon_uuid, address, _page, _escape)

    if path == "/welcome/ack":
        if method == "POST":
            # Nach dem Onboarding ins Forum (Auto-Login greift dort)
            return b"REDIRECT:/forum"
        return b"REDIRECT:/welcome"

    if path == "/welcome":
        import uuid as _uuid
        if identity_uuid:
            anon_uuid = identity_uuid
            return render_welcome_onboarded(anon_uuid, address, _page, _escape)
        elif client_id:
            return render_welcome(address, client_id, request_line)
        else:
            return _page(
                "Willkommen", address,
                "<h1>Willkommen</h1><p>Keine Session. Bitte lade die Seite neu.</p>",
            )

    if path == "/mail":
        import uuid as _uuid
        if identity_uuid:
            anon_uuid = identity_uuid
        elif client_id:
            anon_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))
        else:
            anon_uuid = str(_uuid.uuid4())
        return _render_mail(anon_uuid, address, query=query, method=method, body=body)
    if path == "/forum":
        return render_forum_index(address, client_id, username, admin, identity_uuid, mod=mod)
    if path == "/forum/admin/login":
        return render_forum_admin_login(address, admin_token_value, client_id)

    if path == "/forum/admin":
        return render_forum_admin_dashboard(address, admin, admin_token_value, client_id)

    if path == "/forum/admin/authors":
        return render_forum_admin_authors(address, admin, mod=mod, username=username)

    if path == "/forum/admin/authors/delete" and method == "POST":
        return render_forum_admin_authors_delete(address, admin, body, admin_token_value)

    if path == "/forum/admin/mods":
        return render_forum_admin_mods(address, admin)

    if path == "/forum/admin/mods/set" and method == "POST":
        return render_forum_admin_mods_set(address, admin, body)
    if path == "/forum/search":
        return render_forum_search(address, query)

    # /forum/<category> (nur wenn Kategorie existiert)
    if (path.startswith("/forum/")
            and not path.startswith("/forum/neu")
            and not path.startswith("/forum/search")
            and not path.startswith("/forum/admin")
            and "/" not in path[len("/forum/"):]):
        result = render_forum_category(address, path, query, admin, client_id, mod=mod)
        if result is not None:
            return result

    # --- Auth-Routen ---
    if path == "/forum/login":
        return render_forum_login(address, method, body, client_id)

    if path == "/forum/register":
        return render_forum_register(address, method, body)

    if path == "/forum/logout":
        return render_forum_logout(address, session_token)

    if path == "/forum/my-threads":
        return render_forum_my_threads(address, username)

    # --- Admin: Reports + Mod-Log ---
    if path == "/forum/admin/reports":
        return render_forum_admin_reports(address, admin)

    if path.startswith("/forum/admin/reports/") and path.endswith("/resolve") and method == "POST":
        return render_forum_admin_reports_resolve(address, admin, path, method, admin_token_value)

    if path == "/forum/admin/modlog":
        return render_forum_admin_modlog(address, admin)

    if path == "/forum/health":
        return render_forum_health(address)

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
        return render_forum_admin_bans(address, admin)

    if path == "/forum/admin/ban" and method == "POST":
        return render_forum_admin_ban(address, admin, body, admin_token_value)

    if path == "/forum/admin/promote" and method == "POST":
        return render_forum_admin_promote(address, admin, body, admin_token_value)

    if path.startswith("/forum/admin/bans/") and path.endswith("/unban") and method == "POST":
        return render_forum_admin_bans_unban(address, admin, path, admin_token_value)

    # --- Sticky/Locked-Toggles ---
    if path.startswith("/forum/") and path.endswith("/toggle/sticky") and method == "POST":
        return render_forum_toggle_sticky(address, admin, path)

    if path.startswith("/forum/") and path.endswith("/toggle/locked") and method == "POST":
        return render_forum_toggle_locked(address, admin, path)

    if path == "/forum/neu":
        return render_forum_new_thread(address, method, body, query, client_id)
    if path.startswith("/forum/"):
        return render_forum_thread(address, path, method, body, admin, client_id, mod=mod)
    return _page(
        "404 Nicht gefunden",
        address,
        "<h1>404 — Nicht gefunden</h1><p>Diese Seite existiert nicht.</p>"
        "<a class=\"btn\" href=\"/\">Zur Startseite</a>",
    )


def _render_rotate_confirm(anon_uuid: str, address: str) -> bytes:
    """Bestaetigungsseite fuer Key-Rotation.

    Zeigt: aktuelle Version, Ablaufdatum, Warnung wenn <14 Tage,
    Button 'Ja, jetzt rotieren' (POST /mail/rotate), Link 'Abbrechen' (GET /mail).
    """
    import time as _time
    import datetime as _dt

    # get_or_create: falls die UUID noch keine Keys hat (erster Besuch),
    # werden sie jetzt generiert. Sonst koennte der Nutzer nicht rotieren.
    keys = get_or_create_mail_keys(anon_uuid)
    if not keys:
        return _page(
            "Rotation", address,
            "<h1>Fehler</h1><p>Mail-Keys konnten nicht geladen werden.</p>"
            "<a class=\"btn\" href=\"/mail\">← Zurück</a>",
        )

    version = keys.get("key_version") or 1
    valid_until = keys.get("valid_until")
    days_left = None
    until_str = "(unbekannt)"
    if valid_until:
        seconds_left = valid_until - _time.time()
        days_left = int(seconds_left / 86400)
        until_str = _dt.datetime.fromtimestamp(valid_until).strftime("%Y-%m-%d %H:%M")

    # Warnung bei <14 Tagen
    warning = ""
    if days_left is not None and days_left < 14:
        if days_left < 0:
            warning = (
                "<div style=\"background:#ffe0e0;border:1px solid #cc0000;"
                "padding:10px;margin:10px 0;\">"
                "<strong>⚠ Der aktuelle Schlüssel ist abgelaufen.</strong> "
                "Neue Mails werden als [Signatur abgelaufen] markiert.</div>"
            )
        else:
            warning = (
                "<div style=\"background:#fff4e0;border:1px solid #cc8800;"
                "padding:10px;margin:10px 0;\">"
                f"<strong>⚠ Der aktuelle Schlüssel läuft in {days_left} Tagen ab.</strong></div>"
            )

    html = (
        "<h1>Schlüssel rotieren</h1>"
        "<div style=\"border:1px solid #ccc;padding:15px;margin:10px 0;background:#f9f9f9;\">"
        f"<p><strong>Aktuelle Version:</strong> v{version}</p>"
        f"<p><strong>Gültig bis:</strong> {until_str}</p>"
        f"{warning}"
        "</div>"
        "<div style=\"background:#fff8e0;border:1px solid #cc8800;padding:15px;margin:20px 0;\">"
        "<strong>Was passiert bei der Rotation?</strong>"
        "<ul>"
        "<li>Ein neuer Schlüssel-Satz (v{new}) wird generiert.</li>"
        "<li>Der alte Schlüssel-Satz (v{old}) wird in der History als 'revoked' markiert.</li>"
        "<li>Alle zukünftigen Mails werden mit dem neuen Schlüssel signiert.</li>"
        "<li>Bereits gesendete Mails bleiben lesbar, werden aber als "
        "<strong>[Signatur veraltet]</strong> markiert.</li>"
        "<li>Diese Aktion kann <strong>nicht rückgängig</strong> gemacht werden.</li>"
        "</ul>"
        "</div>"
        "<form method=\"POST\" action=\"/mail/rotate\" style=\"margin:20px 0;\">"
        "<button type=\"submit\" style=\"padding:10px 20px;font-size:16px;"
        "background:#cc3333;color:white;border:none;border-radius:4px;cursor:pointer;\">"
        "Ja, jetzt rotieren"
        "</button>"
        "</form>"
        "<a class=\"btn\" href=\"/mail\">← Abbrechen</a>"
    ).replace("{new}", str(version + 1)).replace("{old}", str(version))

    return _page("Schlüssel rotieren", address, html)


def _handle_rotate_post(anon_uuid: str, address: str) -> bytes:
    """Fuehrt die Rotation aus. Bei Erfolg: Redirect zu /mail?rotated=1."""
    # Rate-Limit pruefen
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
            f"<p>Du hast deine Schluessel zu oft rotiert. "
            f"Bitte warte noch <strong>{retry_min} Minuten</strong> "
            f"({retry_sec} Sekunden), bevor du erneut rotierst.</p>"
            "<a class=\"btn\" href=\"/mail\">← Zurueck</a>",
        )
        # RATE_LIMIT:<retry_after_sec>\n<html>
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
            f"<h1>Rotation nicht möglich</h1><p>{e}</p>"
            "<a class=\"btn\" href=\"/mail\">← Zurück</a>",
        )
    except Exception as e:
        logger.error(f"Rotation unerwartet fehlgeschlagen: {e}")
        return _page(
            "Rotation", address,
            "<h1>Rotation fehlgeschlagen</h1>"
            "<p>Ein unerwarteter Fehler ist aufgetreten.</p>"
            "<a class=\"btn\" href=\"/mail\">← Zurück</a>",
        )



