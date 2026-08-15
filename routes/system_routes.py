"""Operational endpoints.

`/healthz` is what the Application Load Balancer target group checks. It verifies the
database round-trips rather than only that the process is alive, because a web task that
cannot reach RDS should be taken out of rotation.

A cache outage is reported but does **not** make the task unhealthy: the application
degrades to reading from PostgreSQL, so pulling every task out of the load balancer
because ElastiCache is unreachable would turn a slowdown into an outage.
"""

from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from cache import metrics, redis_client
from database.db import get_session
from middleware.auth_middleware import login_required

bp = Blueprint("system", __name__)


@bp.get("/healthz")
def healthz():
    cache_health = redis_client.health()

    try:
        get_session().execute(text("SELECT 1"))
    except SQLAlchemyError:
        return (
            jsonify({"status": "unhealthy", "database": "unavailable", "cache": cache_health}),
            503,
        )

    return jsonify({"status": "ok", "database": "ok", "cache": cache_health})


@bp.get("/api/system/cache")
@login_required
def cache_stats():
    """Cache hit rate for this process.

    Phase 15 reports cache hit rate alongside accuracy and cost; the counters start here
    so that metric is not retrofitted later.
    """
    return jsonify({"cache": redis_client.health(), "counters": metrics.snapshot().to_dict()})
