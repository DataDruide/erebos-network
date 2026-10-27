"""Forum-Seiten: /forum (Hauptseite mit Auto-Login) + /forum/health."""

import logging

from .renderers import _page
from .forum_db import get_identity, get_or_create_forum_session
from . import forum

logger = logging.getLogger(__name__)


def render_forum_index(address: str, client_id: str, username: str,
                       admin: bool = False, identity_uuid: str = "") -> bytes:
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
        "Erebos Community", address,
        forum.render_categories(
            client_id=client_id, username=username,
            admin=admin, admin_token="",
        ),
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


def render_forum_admin_authors(address: str, admin: bool) -> bytes:
    """GET /forum/admin/authors: Autoren-Liste."""
    if not admin:
        return _page(
            "Nicht erlaubt", address,
            "<h1>Nicht erlaubt</h1><p>Admin-Token fehlt.</p>",
        )
    return _page("Autoren", address, forum.render_admin_authors())


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
