"""Authentication endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from database.db import get_session
from middleware.auth_middleware import (
    clear_session_cookie,
    current_context,
    login_required,
    set_session_cookie,
)
from routes.helpers import parse_body
from schemas.auth import LoginRequest, RegisterRequest
from schemas.serializers import serialize_organization, serialize_user
from services import auth_service

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _session_response(context, status_code: int):
    body = {
        "user": serialize_user(context.user),
        "organization": serialize_organization(context.organization, context.role),
    }
    response = jsonify(body)
    response.status_code = status_code
    return set_session_cookie(response, auth_service.create_session_token(context))


@bp.post("/register")
def register():
    payload = parse_body(RegisterRequest)
    context = auth_service.register(get_session(), payload)
    return _session_response(context, 201)


@bp.post("/login")
def login():
    payload = parse_body(LoginRequest)
    context = auth_service.login(get_session(), payload)
    return _session_response(context, 200)


@bp.post("/logout")
def logout():
    # Logout is not authenticated: clearing a cookie should work even if the token has
    # already expired.
    return clear_session_cookie(jsonify({"ok": True}))


@bp.get("/me")
@login_required
def me():
    context = current_context()
    return jsonify(
        {
            "user": serialize_user(context.user),
            "organization": serialize_organization(context.organization, context.role),
        }
    )
