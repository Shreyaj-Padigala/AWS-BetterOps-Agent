"""Database access for projects.

Every read is scoped by `organization_id` in the WHERE clause rather than fetched and
then checked, so a project belonging to another tenant is indistinguishable from one that
does not exist.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import Incident, Project


def get(session: Session, *, project_id: int, organization_id: int) -> Project | None:
    stmt = select(Project).where(
        Project.id == project_id, Project.organization_id == organization_id
    )
    return session.scalars(stmt).first()


def get_by_key(session: Session, *, key: str, organization_id: int) -> Project | None:
    stmt = select(Project).where(
        Project.key == key, Project.organization_id == organization_id
    )
    return session.scalars(stmt).first()


def list_for_organization(session: Session, organization_id: int) -> list[Project]:
    stmt = (
        select(Project)
        .where(Project.organization_id == organization_id)
        .order_by(Project.name)
    )
    return list(session.scalars(stmt))


def count_open_incidents_by_project(
    session: Session, *, organization_id: int, open_statuses: tuple[str, ...]
) -> dict[int, int]:
    """Open-incident counts keyed by project id.

    One aggregate query for the whole organization, so project lists do not issue a
    count per row.
    """
    stmt = (
        select(Incident.project_id, func.count(Incident.id))
        .where(
            Incident.organization_id == organization_id,
            Incident.status.in_(open_statuses),
        )
        .group_by(Incident.project_id)
    )
    return {project_id: count for project_id, count in session.execute(stmt)}


def create(
    session: Session,
    *,
    organization_id: int,
    key: str,
    name: str,
    description: str | None,
    primary_service: str | None,
    repository_url: str | None,
    created_by_user_id: int | None,
) -> Project:
    project = Project(
        organization_id=organization_id,
        key=key,
        name=name,
        description=description,
        primary_service=primary_service,
        repository_url=repository_url,
        created_by_user_id=created_by_user_id,
    )
    session.add(project)
    session.flush()
    return project
