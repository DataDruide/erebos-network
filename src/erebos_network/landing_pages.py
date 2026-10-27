"""HTML-Seiten fuer den Erebos Hidden-Service (Startseite + Wiki)."""

import json
import logging
from pathlib import Path
from typing import Optional

from . import forum
from .onboarding import render_onboard, render_welcome_onboarded, render_recover
from .pages_onboarding import render_welcome, render_landing, render_wiki
from .renderers import _page, _escape, _format_timestamp, _render_identity_box
from .http_utils import http_response, parse_http_request
from .pages_mail import _render_rotate_confirm, _handle_rotate_post, _render_mail
from .pages_forum import (
    render_forum_index, render_forum_health,
    render_forum_login, render_forum_register,
    render_forum_logout,
    render_forum_admin_login, render_forum_admin_dashboard,
    render_forum_admin_authors, render_forum_admin_authors_delete,
    render_forum_admin_reports, render_forum_admin_reports_resolve,
    render_forum_admin_modlog, render_forum_admin_bans,
    render_forum_admin_ban, render_forum_admin_bans_unban,
    render_forum_search, render_forum_my_threads, render_forum_new_thread,
    render_forum_toggle_sticky, render_forum_toggle_locked,
)
from .forum_db import (find_identity_by_identifier, get_or_create_forum_session, load_mails, save_mail, mark_mail_read,
                       get_or_create_mail_keys, get_mail_keys,
                       get_mail_keys_by_version, set_mail_verified,
                       rotate_mail_keys,
                       check_rotate_rate_limit, record_rotate,
                       create_identity, get_identity)
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
                admin_cookie: str = "", identity_uuid: str = "") -> bytes:
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
        elif client_id:
            anon_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))
        else:
            return _page(
                "Willkommen", address,
                "<h1>Willkommen</h1><p>Keine Session. Bitte lade die Seite neu.</p>",
            )
        return render_welcome_onboarded(anon_uuid, address, _page, _escape)

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
        return render_forum_index(address, client_id, username, admin, identity_uuid)
    if path == "/forum/admin/login":
        return render_forum_admin_login(address, admin_token_value, client_id)

    if path == "/forum/admin":
        return render_forum_admin_dashboard(address, admin, admin_token_value, client_id)

    if path == "/forum/admin/authors":
        return render_forum_admin_authors(address, admin)

    if path == "/forum/admin/authors/delete" and method == "POST":
        return render_forum_admin_authors_delete(address, admin, body, admin_token_value)
    if path == "/forum/search":
        return render_forum_search(address, query)

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



