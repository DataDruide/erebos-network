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
