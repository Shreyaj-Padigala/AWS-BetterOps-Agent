"""Page routes, redirects and the health check."""

from __future__ import annotations

import pytest

PROTECTED_PAGES = ["/dashboard", "/projects", "/projects/1", "/incidents", "/incidents/1"]


def test_healthz_reports_ok(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["cache"]["status"] == "ok"


def test_root_redirects_anonymous_visitors_to_login(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_root_redirects_signed_in_users_to_dashboard(signed_in):
    response = signed_in.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


@pytest.mark.parametrize("path", PROTECTED_PAGES)
def test_protected_pages_redirect_to_login(client, path):
    response = client.get(path)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    # The originally requested page is preserved so login can return the user to it.
    assert "next=" in response.headers["Location"]


@pytest.mark.parametrize("path", PROTECTED_PAGES)
def test_protected_pages_render_for_signed_in_users(signed_in, path):
    response = signed_in.get(path)

    assert response.status_code == 200
    assert b"AWS BetterOps Agent" in response.data


def test_login_page_renders(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b"Sign in" in response.data


def test_login_page_redirects_signed_in_users(signed_in):
    response = signed_in.get("/login")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_unknown_api_path_returns_json_error(client):
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_unknown_page_returns_html_error(client):
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert b"404" in response.data


def test_responses_carry_a_request_id(client):
    response = client.get("/healthz")

    assert response.headers.get("X-Request-Id")
