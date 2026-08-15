"""Project endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from database.db import get_session
from middleware.auth_middleware import current_context, login_required
from routes.helpers import parse_body
from schemas.project import CreateProjectRequest, UpdateProjectRequest
from schemas.serializers import serialize_project
from services import project_service

bp = Blueprint("projects", __name__, url_prefix="/api/projects")


@bp.get("")
@login_required
def list_projects():
    context = current_context()
    projects = project_service.list_projects(
        get_session(), organization_id=context.organization.id
    )
    return jsonify(
        {"items": [serialize_project(project, count) for project, count in projects]}
    )


@bp.post("")
@login_required
def create_project():
    context = current_context()
    payload = parse_body(CreateProjectRequest)
    project = project_service.create_project(
        get_session(),
        organization_id=context.organization.id,
        user_id=context.user.id,
        role=context.role,
        payload=payload,
    )
    return jsonify(serialize_project(project, 0)), 201


@bp.get("/<int:project_id>")
@login_required
def get_project(project_id: int):
    context = current_context()
    project = project_service.get_project(
        get_session(), project_id=project_id, organization_id=context.organization.id
    )
    return jsonify(serialize_project(project))


@bp.put("/<int:project_id>")
@login_required
def update_project(project_id: int):
    context = current_context()
    payload = parse_body(UpdateProjectRequest)
    project = project_service.update_project(
        get_session(),
        project_id=project_id,
        organization_id=context.organization.id,
        role=context.role,
        payload=payload,
    )
    return jsonify(serialize_project(project))
