"""Request logging.

Every request gets an id that is attached to its log line and returned in the
`X-Request-Id` header, so a user-reported failure can be traced. Phase 2 replaces the
formatter with JSON output and adds the fields the investigation pipeline needs
(`investigation_id`, `agent`, `tool`).

Nothing here logs a request body, query string values, cookies or headers — those carry
passwords and tokens.
"""

from __future__ import annotations

import logging
import time
import uuid

from flask import Flask, g, request

from middleware.auth_middleware import context_if_loaded

logger = logging.getLogger("betterops.request")

REQUEST_ID_HEADER = "X-Request-Id"


def get_request_id() -> str:
    return getattr(g, "request_id", "-")


def init_app(app: Flask) -> None:
    @app.before_request
    def _start_timer() -> None:
        # Honour an upstream id (the ALB or a caller) so a trace survives hops.
        g.request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        g.request_started_at = time.perf_counter()

    @app.after_request
    def _log_request(response):
        started_at = getattr(g, "request_started_at", None)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2) if started_at else None

        context = context_if_loaded()
        logger.info(
            "%s %s %s %sms",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            extra={
                "request_id": get_request_id(),
                "user_id": context.user.id if context else None,
                "organization_id": context.organization.id if context else None,
                "method": request.method,
                # `request.path` only, never the query string: filters are harmless but
                # a future endpoint could carry a token there.
                "path": request.path,
                "duration_ms": duration_ms,
                "status": response.status_code,
            },
        )
        response.headers[REQUEST_ID_HEADER] = get_request_id()
        return response
