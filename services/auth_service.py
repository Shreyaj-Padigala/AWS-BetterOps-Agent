"""Registration, login and session tokens.

Passwords are hashed with scrypt via `werkzeug.security`, which ships with Flask and is
memory-hard with sensible defaults.

The session is a signed JWT delivered in an HttpOnly cookie (architecture.md §6). Token
creation and verification live here, in one place, so the signing rules cannot drift
between the middleware and anything that issues a token.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from config import get_config
from constants import ROLE_OWNER
from database.models import Organization, OrganizationMember, User
from errors import AuthError, ConflictError
from repositories import organization_repository, user_repository
from schemas.auth import LoginRequest, RegisterRequest

_JWT_ALGORITHM = "HS256"
_SLUG_INVALID = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class AuthenticatedContext:
    """Everything a request needs to know about who is calling."""

    user: User
    organization: Organization
    role: str


def _slugify(value: str) -> str:
    slug = _SLUG_INVALID.sub("-", value.strip().lower()).strip("-")
    return slug or "org"


def _unique_slug(session: Session, base: str) -> str:
    """Append a counter until the slug is free.

    A unique constraint still backs this; the loop only avoids the common collision.
    """
    slug = base[:70]
    suffix = 2
    while organization_repository.get_by_slug(session, slug) is not None:
        slug = f"{base[:66]}-{suffix}"
        suffix += 1
    return slug


def register(session: Session, payload: RegisterRequest) -> AuthenticatedContext:
    """Create a user plus the organization they own.

    Phase 1 gives every new user their own organization. Invitations arrive later; the
    membership table already supports several users per organization.
    """
    email = user_repository.normalize_email(str(payload.email))
    if user_repository.get_by_email(session, email) is not None:
        raise ConflictError("An account with that email already exists.")

    user = user_repository.create(
        session,
        email=email,
        name=payload.name,
        password_hash=generate_password_hash(payload.password),
    )

    organization_name = (payload.organization_name or f"{payload.name}'s Organization").strip()
    organization = organization_repository.create(
        session,
        name=organization_name,
        slug=_unique_slug(session, _slugify(organization_name)),
    )
    membership = organization_repository.add_member(
        session,
        organization_id=organization.id,
        user_id=user.id,
        role=ROLE_OWNER,
    )
    session.commit()
    return AuthenticatedContext(user=user, organization=organization, role=membership.role)


def login(session: Session, payload: LoginRequest) -> AuthenticatedContext:
    user = user_repository.get_by_email(session, str(payload.email))

    # The same message for "no such user" and "wrong password" so the endpoint is not an
    # account-existence oracle.
    invalid = AuthError("Invalid email or password.")
    if user is None or not check_password_hash(user.password_hash, payload.password):
        raise invalid
    if not user.is_active:
        raise AuthError("This account is disabled.")

    return _context_for_user(session, user)


def _context_for_user(session: Session, user: User) -> AuthenticatedContext:
    memberships = organization_repository.list_memberships_for_user(session, user.id)
    if not memberships:
        # Should be impossible: registration always creates one.
        raise AuthError("This account is not a member of any organization.")
    membership: OrganizationMember = memberships[0]
    organization = organization_repository.get_by_id(session, membership.organization_id)
    if organization is None:
        raise AuthError("This account's organization no longer exists.")
    return AuthenticatedContext(user=user, organization=organization, role=membership.role)


def create_session_token(context: AuthenticatedContext) -> str:
    config = get_config()
    issued_at = datetime.now(timezone.utc)
    claims = {
        "sub": str(context.user.id),
        "org": context.organization.id,
        "role": context.role,
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=config.security.session_ttl_seconds),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, config.security.secret_key, algorithm=_JWT_ALGORITHM)


def decode_session_token(token: str) -> dict:
    config = get_config()
    try:
        return jwt.decode(
            token,
            config.security.secret_key,
            algorithms=[_JWT_ALGORITHM],
            options={"require": ["exp", "sub", "org"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Your session is invalid or has expired.") from exc


def load_context_from_claims(session: Session, claims: dict) -> AuthenticatedContext:
    """Rebuild the request context from token claims.

    The membership is re-read on every request rather than trusted from the token, so
    removing a user from an organization takes effect immediately.
    """
    try:
        user_id = int(claims["sub"])
        organization_id = int(claims["org"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError("Your session is invalid or has expired.") from exc

    user = user_repository.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise AuthError("Your session is invalid or has expired.")

    membership = organization_repository.get_membership(
        session, organization_id=organization_id, user_id=user_id
    )
    if membership is None:
        raise AuthError("You are no longer a member of that organization.")

    organization = organization_repository.get_by_id(session, organization_id)
    if organization is None:
        raise AuthError("Your session is invalid or has expired.")

    return AuthenticatedContext(user=user, organization=organization, role=membership.role)
