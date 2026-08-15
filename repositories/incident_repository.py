"""Database access for incidents."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import Incident

# Upper bound on any single page, so a client cannot ask for the whole table.
MAX_PAGE_SIZE = 100


def get(session: Session, *, incident_id: int, organization_id: int) -> Incident | None:
    stmt = select(Incident).where(
        Incident.id == incident_id, Incident.organization_id == organization_id
    )
    return session.scalars(stmt).first()


def list_for_organization(
    session: Session,
    *,
    organization_id: int,
    project_id: int | None = None,
    statuses: tuple[str, ...] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Incident]:
    stmt = select(Incident).where(Incident.organization_id == organization_id)
    if project_id is not None:
        stmt = stmt.where(Incident.project_id == project_id)
    if statuses:
        stmt = stmt.where(Incident.status.in_(statuses))
    stmt = (
        stmt.order_by(Incident.started_at.desc(), Incident.id.desc())
        .limit(min(limit, MAX_PAGE_SIZE))
        .offset(offset)
    )
    return list(session.scalars(stmt).unique())


def count_for_organization(
    session: Session,
    *,
    organization_id: int,
    project_id: int | None = None,
    statuses: tuple[str, ...] | None = None,
) -> int:
    stmt = select(func.count(Incident.id)).where(
        Incident.organization_id == organization_id
    )
    if project_id is not None:
        stmt = stmt.where(Incident.project_id == project_id)
    if statuses:
        stmt = stmt.where(Incident.status.in_(statuses))
    return int(session.scalar(stmt) or 0)


def create(session: Session, incident: Incident) -> Incident:
    session.add(incident)
    session.flush()
    return incident
