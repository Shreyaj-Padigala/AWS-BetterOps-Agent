"""Test fixtures.

The suite runs against in-memory SQLite so it needs no infrastructure. Set
`TEST_DATABASE_URL` to run the same tests against PostgreSQL — the models avoid
PostgreSQL-specific types precisely so both work (architecture.md §5).
"""

from __future__ import annotations

import os

# Must be set before config is first imported: it selects the testing database and
# relaxes the production-only SECRET_KEY requirement.
os.environ["APP_ENV"] = "testing"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-anywhere-real")

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from cache import metrics, redis_client  # noqa: E402
from config import get_config, reset_config_cache  # noqa: E402
from database import db  # noqa: E402
from database.models import Base  # noqa: E402

DEFAULT_PASSWORD = "correct-horse-battery"


def _build_app():
    """Build an application from whatever is currently in the environment.

    Config, database engine, cache backend and cache counters are all reset first, so a
    test that changes an environment variable gets an application that reflects it.
    """
    reset_config_cache()
    db.reset_engine()
    redis_client.reset_backend()
    metrics.reset()

    config = get_config()
    Base.metadata.create_all(db.get_engine())

    flask_app = create_app(config)
    flask_app.config["TESTING"] = True
    return flask_app


def _teardown_app():
    Base.metadata.drop_all(db.get_engine())
    db.reset_engine()
    redis_client.reset_backend()
    metrics.reset()
    reset_config_cache()


@pytest.fixture()
def app():
    flask_app = _build_app()
    yield flask_app
    _teardown_app()


@pytest.fixture()
def app_factory():
    """Build the application *after* a test has set environment overrides.

    Used by tests that need non-default configuration — a low rate limit, a different
    cache backend — which must be in place before the app reads its config.
    """
    yield _build_app
    _teardown_app()


@pytest.fixture()
def client(app):
    return app.test_client()


class ApiClient:
    """Test client wrapper that keeps the session cookie and unwraps JSON."""

    def __init__(self, client):
        self._client = client
        self.user = None
        self.organization = None

    def register(
        self,
        email: str = "engineer@example.com",
        name: str = "Test Engineer",
        password: str = DEFAULT_PASSWORD,
        organization_name: str | None = "Acme Engineering",
    ):
        body = {"email": email, "name": name, "password": password}
        if organization_name:
            body["organization_name"] = organization_name
        response = self._client.post("/api/auth/register", json=body)
        assert response.status_code == 201, response.get_json()
        payload = response.get_json()
        self.user = payload["user"]
        self.organization = payload["organization"]
        return payload

    def create_project(self, key: str = "CHECKOUT", name: str = "Checkout Platform", **extra):
        response = self.post("/api/projects", {"key": key, "name": name, **extra})
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    def create_incident(self, project_id: int, title: str = "Checkout latency spike", **extra):
        response = self.post(
            f"/api/projects/{project_id}/incidents", {"title": title, **extra}
        )
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    def get(self, path: str):
        return self._client.get(path)

    def post(self, path: str, body=None):
        return self._client.post(path, json=body if body is not None else {})

    def put(self, path: str, body=None):
        return self._client.put(path, json=body if body is not None else {})


@pytest.fixture()
def api(app):
    """An unauthenticated API client."""
    return ApiClient(app.test_client())


@pytest.fixture()
def signed_in(api):
    """An API client with a registered, signed-in user."""
    api.register()
    return api


@pytest.fixture()
def other_org(app):
    """A second organization, used to prove tenant isolation."""
    client = ApiClient(app.test_client())
    client.register(
        email="intruder@other.example.com",
        name="Other Engineer",
        organization_name="Other Corp",
    )
    return client
