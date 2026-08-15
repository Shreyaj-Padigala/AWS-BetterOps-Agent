"""Rate limiting: rejection, scope, window reset and behaviour when Redis is down."""

from __future__ import annotations

import pytest

from cache import redis_client
from middleware.rate_limit import WINDOW_SECONDS, RateLimitRule, check
from tests.conftest import DEFAULT_PASSWORD, ApiClient
from tests.test_cache import FailingBackend


@pytest.fixture()
def limited_app(monkeypatch, app_factory):
    """An application with a very low API limit, so the boundary is easy to reach."""
    monkeypatch.setenv("RATE_LIMIT_API_PER_MINUTE", "3")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "50")
    return app_factory()


def _signed_in_client(flask_app, email="engineer@example.com"):
    client = ApiClient(flask_app.test_client())
    client.register(email=email)
    return client


def test_requests_beyond_the_limit_are_rejected(limited_app):
    api = _signed_in_client(limited_app)

    statuses = [api.get("/api/projects").status_code for _ in range(4)]

    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429


def test_rejection_uses_the_standard_error_contract(limited_app):
    api = _signed_in_client(limited_app)
    for _ in range(3):
        api.get("/api/projects")

    response = api.get("/api/projects")

    assert response.status_code == 429
    body = response.get_json()
    assert body["error"]["code"] == "rate_limited"
    # Clients need to know how long to wait, in the body and in the standard header.
    assert body["error"]["details"]["retry_after"] >= 1
    assert int(response.headers["Retry-After"]) >= 1


def test_the_limit_is_per_user_not_global(limited_app):
    first = _signed_in_client(limited_app, email="first@example.com")
    second = _signed_in_client(limited_app, email="second@example.com")

    for _ in range(4):
        first.get("/api/projects")

    # The first user is now blocked; the second must be unaffected.
    assert first.get("/api/projects").status_code == 429
    assert second.get("/api/projects").status_code == 200


def test_the_counter_resets_in_the_next_window(app):
    rule = RateLimitRule("test", limit_per_minute=2)
    now = 1_000_000.0

    check(rule, "user_1", now=now)
    check(rule, "user_1", now=now)
    with pytest.raises(Exception) as exceeded:
        check(rule, "user_1", now=now)
    assert "Rate limit" in str(exceeded.value)

    # A request in the following window gets a fresh counter.
    check(rule, "user_1", now=now + WINDOW_SECONDS)


def test_pages_and_health_checks_are_not_rate_limited(limited_app):
    api = _signed_in_client(limited_app)

    for _ in range(10):
        assert api.get("/dashboard").status_code == 200
        assert api.get("/healthz").status_code == 200


def test_auth_endpoints_are_limited_by_client_address(monkeypatch, app_factory):
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "3")
    flask_app = app_factory()
    client = flask_app.test_client()

    body = {"email": "nobody@example.com", "password": DEFAULT_PASSWORD}
    statuses = [client.post("/api/auth/login", json=body).status_code for _ in range(4)]

    # Failed logins still consume the budget — that is the point of limiting them.
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429


def test_limiting_can_be_turned_off(monkeypatch, app_factory):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_API_PER_MINUTE", "1")
    api = _signed_in_client(app_factory())

    statuses = [api.get("/api/projects").status_code for _ in range(5)]

    assert statuses == [200] * 5


def test_limiting_fails_open_when_the_backend_is_down(limited_app):
    api = _signed_in_client(limited_app)
    redis_client.set_backend(FailingBackend())

    # A cache outage must not become an outage of the whole API.
    statuses = [api.get("/api/projects").status_code for _ in range(6)]

    assert statuses == [200] * 6
