"""Incident business logic.

From Phase 8 an incident is the entry point of an investigation, so the fields agents
depend on — `started_at`, `affected_service`, `severity` — are treated as first-class
here rather than as free-text notes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from cache import cache_service
from config import get_config
from constants import (
    INCIDENT_STATUSES,
    INCIDENT_TERMINAL_STATUSES,
    SOURCE_MANUAL,
)
from database.models import Incident
from errors import NotFoundError, ValidationError
from repositories import incident_repository
from schemas.incident import CreateIncidentRequest, UpdateIncidentRequest
from schemas.serializers import serialize_incident
from services import project_service
from services.project_service import OPEN_STATUSES

DEFAULT_PAGE_SIZE = 25
RECENT_INCIDENTS_ON_DASHBOARD = 8


def list_incidents(
    session: Session,
    *,
    organization_id: int,
    project_id: int | None = None,
    status: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> tuple[list[Incident], int]:
    """Return a page of incidents plus the total matching count."""
    if project_id is not None:
        # Raises NotFoundError if the project belongs to another organization, which
        # keeps project ids from being probed through the incident list.
        project_service.get_project(
            session, project_id=project_id, organization_id=organization_id
        )

    statuses = _statuses_for_filter(status)
    incidents = incident_repository.list_for_organization(
        session,
        organization_id=organization_id,
        project_id=project_id,
        statuses=statuses,
        limit=limit,
        offset=offset,
    )
    total = incident_repository.count_for_organization(
        session,
        organization_id=organization_id,
        project_id=project_id,
        statuses=statuses,
    )
    return incidents, total


def _statuses_for_filter(status: str | None) -> tuple[str, ...] | None:
    if status is None or status == "":
        return None
    normalized = status.upper()
    if normalized == "OPEN_ONLY":
        return OPEN_STATUSES
    if normalized not in INCIDENT_STATUSES:
        raise ValidationError(
            "Unknown status filter.",
            {"status": f"Must be one of {', '.join(INCIDENT_STATUSES)} or OPEN_ONLY."},
        )
    return (normalized,)


def get_incident(session: Session, *, incident_id: int, organization_id: int) -> Incident:
    """The incident record itself. Always read from PostgreSQL."""
    incident = incident_repository.get(
        session, incident_id=incident_id, organization_id=organization_id
    )
    if incident is None:
        raise NotFoundError("Incident not found.")
    return incident


def get_incident_view(
    session: Session, *, incident_id: int, organization_id: int
) -> dict[str, Any]:
    """The serialised incident, read through the cache.

    Detail pages are polled — heavily so once Phase 9 adds investigation progress — and
    an incident changes rarely between polls. The cached value is the response payload
    rather than the ORM object: a detached model would need re-attaching, and caching a
    dict keeps the cached shape identical to the API contract.

    A `NotFoundError` from the loader propagates and nothing is stored, so a missing
    incident is never cached as if it existed.
    """
    cache_key = cache_service.incident_key(organization_id, incident_id)

    def load() -> dict[str, Any]:
        incident = get_incident(
            session, incident_id=incident_id, organization_id=organization_id
        )
        return serialize_incident(incident)

    return cache_service.get_or_set(
        cache_key, get_config().cache.ttl_incident, load
    )


def create_incident(
    session: Session,
    *,
    organization_id: int,
    project_id: int,
    user_id: int,
    payload: CreateIncidentRequest,
    source: str = SOURCE_MANUAL,
) -> Incident:
    project = project_service.get_project(
        session, project_id=project_id, organization_id=organization_id
    )

    incident = Incident(
        organization_id=organization_id,
        project_id=project.id,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        source=source,
        # Fall back to the project's primary service so triage has something to work
        # with when the reporter did not specify one.
        affected_service=payload.affected_service or project.primary_service,
        started_at=payload.started_at or datetime.now(timezone.utc),
    )
    incident.created_by_user_id = user_id

    incident_repository.create(session, incident)
    session.commit()
    return incident


def update_incident(
    session: Session,
    *,
    incident_id: int,
    organization_id: int,
    payload: UpdateIncidentRequest,
) -> Incident:
    incident = get_incident(
        session, incident_id=incident_id, organization_id=organization_id
    )

    changes = payload.model_dump(exclude_unset=True)
    new_status = changes.get("status")

    for field, value in changes.items():
        setattr(incident, field, value)

    if new_status is not None:
        _apply_status_side_effects(incident, new_status)

    session.commit()

    # Invalidate after the commit, never before: a reader racing an in-flight
    # transaction would otherwise repopulate the cache with the pre-update row.
    cache_service.invalidate(cache_service.incident_key(organization_id, incident_id))
    return incident


def _apply_status_side_effects(incident: Incident, new_status: str) -> None:
    """Keep `resolved_at` consistent with the status.

    Resolution time is a metric the evaluation platform reports on, so it is derived
    from the status transition rather than left to the caller to remember.
    """
    if new_status in INCIDENT_TERMINAL_STATUSES:
        if incident.resolved_at is None:
            incident.resolved_at = datetime.now(timezone.utc)
    else:
        incident.resolved_at = None


def dashboard_summary(session: Session, *, organization_id: int) -> dict[str, Any]:
    open_incidents = incident_repository.count_for_organization(
        session, organization_id=organization_id, statuses=OPEN_STATUSES
    )
    total_incidents = incident_repository.count_for_organization(
        session, organization_id=organization_id
    )
    recent = incident_repository.list_for_organization(
        session, organization_id=organization_id, limit=RECENT_INCIDENTS_ON_DASHBOARD
    )
    projects = project_service.list_projects(session, organization_id=organization_id)

    return {
        "open_incidents": open_incidents,
        "total_incidents": total_incidents,
        "project_count": len(projects),
        "recent_incidents": recent,
        # Phase 9 replaces this with real investigation counts.
        "active_investigations": 0,
    }
