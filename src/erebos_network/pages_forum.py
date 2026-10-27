"""Forum-Seiten: /forum (Hauptseite mit Auto-Login) + /forum/health."""

import logging

from .renderers import _page
from .forum_db import get_identity, get_or_create_forum_session
from . import forum

logger = logging.getLogger(__name__)


def render_forum_index(address: str, client_id: str, username: str,
                       admin: bool = False, identity_uuid: str = "",
                       mod: bool = False) -> bytes:
    """GET /forum: Auto-Login nach Onboarding + Kategorien-Liste.

    Returns:
        Entweder REDIRECT:/forum mit SET_SESSION-Cookie (wenn Auto-Login
        stattfindet) oder die Kategorien-Seite.
    """
    import uuid as _uuid
    if not username:
        if identity_uuid:
            anon_uuid = identity_uuid
        elif client_id:
            anon_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "erebos-" + client_id))
        else:
            anon_uuid = ""
        if anon_uuid:
            ident = get_identity(anon_uuid)
            if ident and ident.get("onboarded_at"):
                session = get_or_create_forum_session(anon_uuid)
                if session:
                    logger.info(
                        f"Auto-Login Forum: {anon_uuid[:8]} -> {session['username']}"
                    )
                    return (
                        b"REDIRECT:/forum\n"
                        + b"SET_SESSION:" + session["token"].encode() + b"\n"
                        + b"SET_ADMIN:0"
                    )
    return _page(
        "EREBOS COMMUNITY", address,
        forum.render_categories(
            client_id=client_id, username=username,
            admin=admin, admin_token="", mod=mod,
        ),
        hero_image="community-bg.jpeg",
    )


def render_forum_health(address: str) -> bytes:
    """GET /forum/health: Health-Status."""
    return _page("Health", address, forum.render_health())


def render_forum_login(address: str, method: str = "GET", body: bytes = b"",
                       client_id: str = "") -> bytes:
    """GET/POST /forum/login: Login-Formular + Verarbeitung."""
    if method == "POST":
        form = forum.parse_form_body(body)
        token, reason = forum.login_user(
            form.get("username", ""), form.get("password", ""),
            client_id=client_id,
        )
        if token:
            return b"REDIRECT:/forum\nSET_SESSION:" + token.encode("utf-8")
        if reason == "rate_limit":
            return b"RATE_LIMIT:1"
        return _page(
            "Login", address,
            forum.render_login_form("Login fehlgeschlagen."),
        )
    return _page("Login", address, forum.render_login_form())


def render_forum_register(address: str, method: str = "GET", body: bytes = b"") -> bytes:
    """GET/POST /forum/register: Registrierungs-Formular + Verarbeitung."""
    if method == "POST":
        form = forum.parse_form_body(body)
        ok, msg = forum.register_user(
            form.get("username", ""), form.get("password", "")
        )
        if ok:
            return b"REDIRECT:/forum/login"
        return _page("Registrieren", address, forum.render_register_form(msg))
    return _page("Registrieren", address, forum.render_register_form())


def render_forum_logout(address: str, session_token: str) -> bytes:
    """GET /forum/logout: Session loeschen + Redirect."""
    forum.logout_user(session_token)
    return b"REDIRECT:/forum\nCLEAR_SESSION:1"


def render_forum_admin_login(address: str, admin_token_value: str,
                             client_id: str) -> bytes:
    """GET /forum/admin/login: setzt das Admin-Cookie."""
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


def render_forum_admin_dashboard(address: str, admin: bool,
                                 admin_token_value: str,
                                 client_id: str) -> bytes:
    """GET /forum/admin: Admin-Status."""
    if not admin:
        return _page(
            "Nicht erlaubt", address,
            "<h1>Nicht erlaubt</h1>"
            "<p>Admin-Token fehlt oder ist falsch.</p>"
            "<a class=\"btn\" href=\"/forum\">\u2190 Zur\u00fcck</a>",
        )
    return _page(
        "Admin", address,
        forum.render_admin_status(
            client_id=client_id, admin_token=admin_token_value
        ),
    )


def render_forum_admin_authors(address: str, admin: bool,
                                mod: bool = False, username: str = "") -> bytes:
    """GET /forum/admin/authors: Autoren-Liste (Admin: alle, Mod: nur eigene Kategorien)."""
    if not admin and not mod:
        return _page(
            "Nicht erlaubt", address,
            "<h1>Nicht erlaubt</h1><p>Admin- oder Mod-Rechte erforderlich.</p>",
        )
    return _page(
        "Autoren", address,
        forum.render_admin_authors(admin=admin, username=username),
    )


def render_forum_admin_authors_delete(address: str, admin: bool,
                                      body: bytes,
                                      admin_token_value: str) -> bytes:
    """POST /forum/admin/authors/delete: Autor loeschen."""
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


def render_forum_search(address: str, query: str = "") -> bytes:
    """GET /forum/search: Suchergebnisse."""
    from urllib.parse import parse_qs as _pq
    q = ""
    if query:
        q = (_pq(query).get("q", [""])[0] or "")
    results = forum.search_threads(q)
    return _page(
        f"Suche: {q}", address,
        forum.render_search_results(q, results),
    )


def render_forum_my_threads(address: str, username: str) -> bytes:
    """GET /forum/my-threads: eigene Threads (Redirect zu /login wenn nicht eingeloggt)."""
    if not username:
        return b"REDIRECT:/forum/login"
    return _page("Meine Threads", address, forum.render_my_threads(username))


def render_forum_new_thread(address: str, method: str = "GET", body: bytes = b"",
                            query: str = "", client_id: str = "") -> bytes:
    """GET/POST /forum/neu: neuer Thread."""
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
            "Fehler", address,
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


def render_forum_admin_reports(address: str, admin: bool) -> bytes:
    """GET /forum/admin/reports: Meldungen-Liste."""
    if not admin:
        return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
    return _page("Meldungen", address, forum.render_reports())


def render_forum_admin_reports_resolve(address: str, admin: bool,
                                       path: str, method: str,
                                       admin_token_value: str) -> bytes:
    """POST /forum/admin/reports/<idx>/resolve."""
    if not admin:
        return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
    idx_str = path[len("/forum/admin/reports/"):-len("/resolve")]
    try:
        idx = int(idx_str)
    except ValueError:
        idx = -1
    forum.resolve_report(idx)
    return b"REDIRECT:/forum/admin/reports?admin=" + admin_token_value.encode("utf-8")


def render_forum_admin_modlog(address: str, admin: bool) -> bytes:
    """GET /forum/admin/modlog: Moderations-Log."""
    if not admin:
        return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
    return _page("Mod-Log", address, forum.render_mod_log())


def render_forum_admin_bans(address: str, admin: bool) -> bytes:
    """GET /forum/admin/bans: Ban-Liste."""
    if not admin:
        return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
    return _page("Ban-Liste", address, forum.render_bans())


def render_forum_admin_ban(address: str, admin: bool, body: bytes,
                           admin_token_value: str) -> bytes:
    """POST /forum/admin/ban: Nutzer bannen."""
    if not admin:
        return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
    form = forum.parse_form_body(body)
    username = form.get("username", "")
    reason = form.get("reason", "")
    forum.ban_user(username, reason)
    forum.log_moderation("ban", username, "admin")
    return b"REDIRECT:/forum/admin/bans?admin=" + admin_token_value.encode("utf-8")


def render_forum_admin_bans_unban(address: str, admin: bool, path: str,
                                  admin_token_value: str) -> bytes:
    """POST /forum/admin/bans/<idx>/unban: Ban aufheben."""
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


def render_forum_toggle_sticky(address: str, admin: bool, path: str) -> bytes:
    """POST /forum/<tid>/toggle/sticky: Thread anpinnen/loesen."""
    if not admin:
        return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
    tid = path[len("/forum/"):-len("/toggle/sticky")]
    forum.toggle_sticky(tid)
    forum.log_moderation("sticky", tid, "admin")
    return b"REDIRECT:/forum/" + tid.encode("utf-8")


def render_forum_toggle_locked(address: str, admin: bool, path: str) -> bytes:
    """POST /forum/<tid>/toggle/locked: Thread sperren/entsperren."""
    if not admin:
        return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
    tid = path[len("/forum/"):-len("/toggle/locked")]
    forum.toggle_locked(tid)
    forum.log_moderation("locked", tid, "admin")
    return b"REDIRECT:/forum/" + tid.encode("utf-8")


def render_forum_category(address: str, path: str, query: str,
                          admin: bool, client_id: str, mod: bool = False):
    """GET /forum/<category>: Kategorie-Liste.

    Returns:
        bytes, wenn die Kategorie existiert.
        None, wenn die Kategorie nicht existiert (-> naechster Block).
    """
    cat_slug = path[len("/forum/"):]
    cat = forum.get_category(cat_slug)
    if cat is None:
        return None
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
        cat["name"],
        address,
        forum.render_thread_list(
            cat_slug, page=page_n, sort=sort,
            admin=admin, client_id=client_id, mod=mod,
        ),
    )


def render_forum_thread(address: str, path: str, method: str = "GET",
                        body: bytes = b"", admin: bool = False,
                        client_id: str = "", mod: bool = False) -> bytes:
    """GET/POST /forum/<id> mit Unterrouten (antwort, delete, edit, post/*)."""
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
    return _page(t["title"], address, forum.render_thread(t, admin=admin, mod=mod))


def render_forum_admin_promote(address: str, admin: bool, body: bytes,
                               admin_token_value: str) -> bytes:
    """POST /forum/admin/promote: Rolle eines Users setzen."""
    if not admin:
        return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
    form = forum.parse_form_body(body)
    username = form.get("username", "")
    role = form.get("role", "user")
    if role not in ("admin", "mod", "user"):
        return _page("Fehler", address, "<h1>Ungueltige Rolle</h1>")
    from .forum_db import set_user_role
    if set_user_role(username, role):
        forum.log_moderation("promote", f"{username} zu {role}", "admin")
        return b"REDIRECT:/forum/admin/authors?admin=" + admin_token_value.encode("utf-8")
    return _page("Fehler", address, "<h1>User nicht gefunden</h1>")


def render_forum_admin_mods(address: str, admin: bool) -> bytes:
    """GET /forum/admin/mods: Moderator-Verwaltung."""
    if not admin:
        return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
    return _page(
        "Moderator-Verwaltung", address,
        forum.render_mods_management(admin=admin),
    )


def render_forum_admin_mods_set(address: str, admin: bool, body: bytes) -> bytes:
    """POST /forum/admin/mods/set: Kategorien setzen."""
    if not admin:
        return _page("Nicht erlaubt", address, "<h1>Nicht erlaubt</h1>")
    from urllib.parse import parse_qs
    qs = parse_qs(body.decode("utf-8", "replace"))
    username = (qs.get("username", [""])[0] or "").strip()
    category_ids = qs.get("categories", [])
    if not username:
        return _page("Fehler", address, "<h1>Username fehlt</h1>")
    return forum.render_mods_set(username, category_ids, admin=admin)
