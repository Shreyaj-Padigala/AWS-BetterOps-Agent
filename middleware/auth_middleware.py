"""Session cookie handling and route protection.

The session token is a signed JWT in an HttpOnly cookie. It is never exposed to
JavaScript, so an XSS bug cannot read it, and `SameSite=Strict` means a cross-site
request cannot carry it (architecture.md §6).

Two decorators exist because the two kinds of route fail differently:

* `login_required`   — JSON endpoints, answers 401 with the standard error body.
* `page_login_required` — HTML pages, redirects to the login page.
"""

from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import Response, g, redirect, request, url_for

from config import get_config
from database.db import get_session
from errors import AuthError
from services import auth_service
from services.auth_service import AuthenticatedContext

_CONTEXT_KEY = "auth_context"


def set_session_cookie(response: Response, token: str) -> Response:
    config = get_config()
    response.set_cookie(
        config.security.session_cookie_name,
        token,
        max_age=config.security.session_ttl_seconds,
        httponly=True,
        secure=config.security.cookie_secure,
        samesite=config.security.cookie_samesite,
        path="/",
    )
    return response


def clear_session_cookie(response: Response) -> Response:
    config = get_config()
    response.delete_cookie(
        config.security.session_cookie_name,
        path="/",
        httponly=True,
        secure=config.security.cookie_secure,
        samesite=config.security.cookie_samesite,
    )
    return response


def load_context() -> AuthenticatedContext:
    """Resolve the caller from the session cookie, caching it on the request.

    Raises `AuthError` when there is no valid session.
    """
    cached = getattr(g, _CONTEXT_KEY, None)
    if cached is not None:
        return cached

    config = get_config()
    token = request.cookies.get(config.security.session_cookie_name)
    if not token:
        raise AuthError("Authentication required.")

    claims = auth_service.decode_session_token(token)
    context = auth_service.load_context_from_claims(get_session(), claims)
    setattr(g, _CONTEXT_KEY, context)
    return context


def current_context() -> AuthenticatedContext:
    """The authenticated caller. Only valid inside a protected route."""
    context = context_if_loaded()
    if context is None:
        raise AuthError("Authentication required.")
    return context


def context_if_loaded() -> AuthenticatedContext | None:
    """The context if this request already resolved one, without trying to resolve it.

    Used by the logging middleware, which must not trigger authentication itself.
    """
    return getattr(g, _CONTEXT_KEY, None)


def optional_context() -> AuthenticatedContext | None:
    """The caller if signed in, otherwise None. Used by pages that render either way."""
    try:
        return load_context()
    except AuthError:
        return None


def login_required(view: Callable) -> Callable:
    """Protect a JSON endpoint."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        load_context()
        return view(*args, **kwargs)

    return wrapper


def page_login_required(view: Callable) -> Callable:
    """Protect an HTML page, redirecting anonymous visitors to the login page."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            load_context()
        except AuthError:
            return redirect(url_for("pages.login_page", next=request.path))
        return view(*args, **kwargs)

    return wrapper
