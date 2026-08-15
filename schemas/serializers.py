"""Model to JSON conversion.

Serialisation lives here rather than on the models so the API response shape is a
deliberate contract instead of a side effect of the database schema.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from database.models import Incident, Organization, Project, User


def iso(value: datetime | None) -> str | None:
    """ISO-8601 in UTC. Naive values are assumed to be UTC (see architecture.md §5)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "created_at": iso(user.created_at),
    }


def serialize_organization(organization: Organization, role: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": organization.id,
        "name": organization.name,
        "slug": organization.slug,
    }
    if role is not None:
        payload["role"] = role
    return payload


def serialize_project(project: Project, open_incident_count: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": project.id,
        "key": project.key,
        "name": project.name,
        "description": project.description,
        "primary_service": project.primary_service,
        "repository_url": project.repository_url,
        "created_at": iso(project.created_at),
        "updated_at": iso(project.updated_at),
    }
    if open_incident_count is not None:
        payload["open_incident_count"] = open_incident_count
    return payload


def serialize_incident(incident: Incident) -> dict[str, Any]:
    return {
        "id": incident.id,
        # Display identifier. Derived rather than stored, which avoids a per-project
        # counter and the race that comes with it.
        "reference": f"INC-{incident.id}",
        "title": incident.title,
        "description": incident.description,
        "severity": incident.severity,
        "status": incident.status,
        "source": incident.source,
        "affected_service": incident.affected_service,
        "started_at": iso(incident.started_at),
        "resolved_at": iso(incident.resolved_at),
        "created_at": iso(incident.created_at),
        "updated_at": iso(incident.updated_at),
        "project": {
            "id": incident.project_id,
            "key": incident.project.key if incident.project else None,
            "name": incident.project.name if incident.project else None,
        },
    }
