"""Database access for users."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_by_email(session: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == normalize_email(email))
    return session.scalars(stmt).first()


def create(session: Session, *, email: str, name: str, password_hash: str) -> User:
    user = User(email=normalize_email(email), name=name.strip(), password_hash=password_hash)
    session.add(user)
    session.flush()
    return user
