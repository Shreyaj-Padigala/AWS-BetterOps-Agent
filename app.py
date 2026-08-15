"""Application factory and development entrypoint.

Deliberately small: it wires components together and owns nothing else. Business logic
lives in `services/`, data access in `repositories/`, HTTP handling in `routes/`.
"""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from config import Config, get_config
from database import db
from errors import ApiError, RateLimitError
from logging_config import configure_logging
from middleware import rate_limit, request_logging
from routes import (
    auth_routes,
    dashboard_routes,
    incident_routes,
    page_routes,
    project_routes,
    system_routes,
)

# Request bodies larger than this are rejected before they reach a handler.
MAX_CONTENT_LENGTH = 1 * 1024 * 1024


def create_app(config: Config | None = None) -> Flask:
    config = config or get_config()
    configure_logging(config)

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = config.security.secret_key
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["BETTEROPS_CONFIG"] = config
    # Keys are already ordered meaningfully by the serialisers.
    app.json.sort_keys = False

    db.init_app(app)
    # Order matters: the request id is assigned first so every later hook, including a
    # rate-limit rejection, logs under it.
    request_logging.init_app(app)
    rate_limit.init_app(app)

    app.register_blueprint(system_routes.bp)
    app.register_blueprint(page_routes.bp)
    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(project_routes.bp)
    app.register_blueprint(incident_routes.bp)
    app.register_blueprint(dashboard_routes.bp)

    _register_error_handlers(app)
    return app


def _wants_json() -> bool:
    """API clients get JSON; browsers hitting a page get HTML."""
    if request.path.startswith("/api/"):
        return True
    return request.accept_mimetypes.best == "application/json"


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _handle_api_error(error: ApiError):
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        if isinstance(error, RateLimitError):
            response.headers["Retry-After"] = str(error.retry_after)
        return response

    @app.errorhandler(HTTPException)
    def _handle_http_exception(error: HTTPException):
        if _wants_json():
            body = {
                "error": {
                    "code": (error.name or "error").lower().replace(" ", "_"),
                    "message": error.description or "Request failed.",
                    "details": {},
                }
            }
            return jsonify(body), error.code or 500
        return render_template("error.html", code=error.code, message=error.name), error.code

    @app.errorhandler(Exception)
    def _handle_unexpected(error: Exception):
        # The message and traceback stay in the logs; the client gets nothing that could
        # leak internals.
        app.logger.exception("Unhandled exception: %s", error)
        if _wants_json():
            body = {
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong. The error has been logged.",
                    "details": {},
                }
            }
            return jsonify(body), 500
        return render_template("error.html", code=500, message="Internal Server Error"), 500


if __name__ == "__main__":
    app_config = get_config()
    create_app(app_config).run(
        host=app_config.host,
        port=app_config.port,
        debug=app_config.is_development,
    )
