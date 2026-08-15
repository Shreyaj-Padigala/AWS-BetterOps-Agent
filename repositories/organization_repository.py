"""Database access for organizations and their membership."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from constants import ROLE_MEMBER
from database.models import Organization, OrganizationMember


def get_by_id(session: Session, organization_id: int) -> Organization | None:
    return session.get(Organization, organization_id)


def get_by_slug(session: Session, slug: str) -> Organization | None:
    stmt = select(Organization).where(Organization.slug == slug)
    return session.scalars(stmt).first()


def create(session: Session, *, name: str, slug: str) -> Organization:
    organization = Organization(name=name.strip(), slug=slug)
    session.add(organization)
    session.flush()
    return organization


def add_member(
    session: Session, *, organization_id: int, user_id: int, role: str = ROLE_MEMBER
) -> OrganizationMember:
    member = OrganizationMember(
        organization_id=organization_id, user_id=user_id, role=role
    )
    session.add(member)
    session.flush()
    return member


def get_membership(
    session: Session, *, organization_id: int, user_id: int
) -> OrganizationMember | None:
    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == organization_id,
        OrganizationMember.user_id == user_id,
    )
    return session.scalars(stmt).first()


def list_memberships_for_user(session: Session, user_id: int) -> list[OrganizationMember]:
    stmt = (
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user_id)
        .order_by(OrganizationMember.id)
    )
    return list(session.scalars(stmt))
