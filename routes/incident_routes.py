"""Incident endpoints.

Paths follow the resource hierarchy: incidents are created under a project, then
addressed directly by id.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from database.db import get_session
from middleware.auth_middleware import current_context, login_required
from repositories.incident_repository import MAX_PAGE_SIZE
from routes.helpers import paginated, parse_body, query_int
from schemas.incident import CreateIncidentRequest, UpdateIncidentRequest
from schemas.serializers import serialize_incident
from services import incident_service

bp = Blueprint("incidents", __name__, url_prefix="/api")


def _list(project_id: int | None):
    context = current_context()
    limit = query_int("limit", incident_service.DEFAULT_PAGE_SIZE, minimum=1, maximum=MAX_PAGE_SIZE)
    offset = query_int("offset", 0, minimum=0, maximum=100_000)

    incidents, total = incident_service.list_incidents(
        get_session(),
        organization_id=context.organization.id,
        project_id=project_id,
        status=request.args.get("status"),
        limit=limit,
        offset=offset,
    )
    return jsonify(
        paginated([serialize_incident(incident) for incident in incidents], total, limit, offset)
    )


@bp.get("/incidents")
@login_required
def list_all_incidents():
    return _list(project_id=None)


@bp.get("/projects/<int:project_id>/incidents")
@login_required
def list_project_incidents(project_id: int):
    return _list(project_id=project_id)


@bp.post("/projects/<int:project_id>/incidents")
@login_required
def create_incident(project_id: int):
    context = current_context()
    payload = parse_body(CreateIncidentRequest)
    incident = incident_service.create_incident(
        get_session(),
        organization_id=context.organization.id,
        project_id=project_id,
        user_id=context.user.id,
        payload=payload,
    )
    return jsonify(serialize_incident(incident)), 201


@bp.get("/incidents/<int:incident_id>")
@login_required
def get_incident(incident_id: int):
    context = current_context()
    # Served through the cache; the service returns the response payload directly.
    return jsonify(
        incident_service.get_incident_view(
            get_session(), incident_id=incident_id, organization_id=context.organization.id
        )
    )


@bp.put("/incidents/<int:incident_id>")
@login_required
def update_incident(incident_id: int):
    context = current_context()
    payload = parse_body(UpdateIncidentRequest)
    incident = incident_service.update_incident(
        get_session(),
        incident_id=incident_id,
        organization_id=context.organization.id,
        payload=payload,
    )
    return jsonify(serialize_incident(incident))
