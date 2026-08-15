"""Project business logic."""

from __future__ import annotations

from sqlalchemy.orm import Session

from constants import INCIDENT_TERMINAL_STATUSES, INCIDENT_STATUSES, PROJECT_WRITE_ROLES
from database.models import Project
from errors import ConflictError, ForbiddenError, NotFoundError
from repositories import project_repository
from schemas.project import CreateProjectRequest, UpdateProjectRequest

# Statuses that count as "needs attention" on dashboards and project cards.
OPEN_STATUSES = tuple(s for s in INCIDENT_STATUSES if s not in INCIDENT_TERMINAL_STATUSES)


def _require_write_role(role: str) -> None:
    if role not in PROJECT_WRITE_ROLES:
        raise ForbiddenError("Only organization owners and admins can modify projects.")


def list_projects(session: Session, *, organization_id: int) -> list[tuple[Project, int]]:
    """Projects with their open-incident counts, newest counts in one aggregate query."""
    projects = project_repository.list_for_organization(session, organization_id)
    counts = project_repository.count_open_incidents_by_project(
        session, organization_id=organization_id, open_statuses=OPEN_STATUSES
    )
    return [(project, counts.get(project.id, 0)) for project in projects]


def get_project(session: Session, *, project_id: int, organization_id: int) -> Project:
    project = project_repository.get(
        session, project_id=project_id, organization_id=organization_id
    )
    if project is None:
        raise NotFoundError("Project not found.")
    return project


def create_project(
    session: Session,
    *,
    organization_id: int,
    user_id: int,
    role: str,
    payload: CreateProjectRequest,
) -> Project:
    _require_write_role(role)

    existing = project_repository.get_by_key(
        session, key=payload.key, organization_id=organization_id
    )
    if existing is not None:
        raise ConflictError(f"A project with key {payload.key} already exists.")

    project = project_repository.create(
        session,
        organization_id=organization_id,
        key=payload.key,
        name=payload.name,
        description=payload.description,
        primary_service=payload.primary_service,
        repository_url=payload.repository_url,
        created_by_user_id=user_id,
    )
    session.commit()
    return project


def update_project(
    session: Session,
    *,
    project_id: int,
    organization_id: int,
    role: str,
    payload: UpdateProjectRequest,
) -> Project:
    _require_write_role(role)
    project = get_project(
        session, project_id=project_id, organization_id=organization_id
    )

    # Only fields the client actually sent are applied, so a partial update cannot blank
    # out a field by omission.
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)

    session.commit()
    return project
