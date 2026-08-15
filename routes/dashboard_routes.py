"""Dashboard summary endpoint.

Kept separate from the incident endpoints because the dashboard is a read model that
will grow to include investigation and integration state in later phases.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from database.db import get_session
from middleware.auth_middleware import current_context, login_required
from schemas.serializers import serialize_incident
from services import incident_service

bp = Blueprint("dashboard", __name__, url_prefix="/api")


@bp.get("/dashboard")
@login_required
def dashboard():
    context = current_context()
    summary = incident_service.dashboard_summary(
        get_session(), organization_id=context.organization.id
    )
    return jsonify(
        {
            "open_incidents": summary["open_incidents"],
            "total_incidents": summary["total_incidents"],
            "project_count": summary["project_count"],
            "active_investigations": summary["active_investigations"],
            "recent_incidents": [
                serialize_incident(incident) for incident in summary["recent_incidents"]
            ],
        }
    )
