"""Registration, login, session cookie and logout."""

from __future__ import annotations

from tests.conftest import DEFAULT_PASSWORD


def test_register_creates_user_and_organization(api):
    payload = api.register()

    assert payload["user"]["email"] == "engineer@example.com"
    assert payload["organization"]["name"] == "Acme Engineering"
    # The first user owns the organization they created.
    assert payload["organization"]["role"] == "owner"


def test_register_sets_httponly_session_cookie(app, api):
    response = api._client.post(
        "/api/auth/register",
        json={
            "email": "cookie@example.com",
            "name": "Cookie Tester",
            "password": DEFAULT_PASSWORD,
        },
    )

    assert response.status_code == 201
    cookie_header = response.headers["Set-Cookie"]
    assert app.config["BETTEROPS_CONFIG"].security.session_cookie_name in cookie_header
    # The token must be unreachable from JavaScript and unusable cross-site.
    assert "HttpOnly" in cookie_header
    assert "SameSite=Strict" in cookie_header


def test_register_rejects_duplicate_email(api):
    api.register()
    response = api.post(
        "/api/auth/register",
        {"email": "engineer@example.com", "name": "Someone Else", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "conflict"


def test_register_rejects_short_password(api):
    response = api.post(
        "/api/auth/register",
        {"email": "weak@example.com", "name": "Weak", "password": "short"},
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "validation_error"
    assert "password" in body["error"]["details"]


def test_register_rejects_invalid_email(api):
    response = api.post(
        "/api/auth/register",
        {"email": "not-an-email", "name": "Nobody", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 400
    assert "email" in response.get_json()["error"]["details"]


def test_register_requires_a_json_body(client):
    response = client.post("/api/auth/register", data="not json", content_type="text/plain")
    assert response.status_code == 400


def test_login_succeeds_with_correct_password(app, api):
    api.register()
    fresh = app.test_client()

    response = fresh.post(
        "/api/auth/login",
        json={"email": "engineer@example.com", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == "engineer@example.com"


def test_login_rejects_wrong_password(app, api):
    api.register()
    fresh = app.test_client()

    response = fresh.post(
        "/api/auth/login", json={"email": "engineer@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401
    # The same message as an unknown account, so this is not an existence oracle.
    assert response.get_json()["error"]["message"] == "Invalid email or password."


def test_login_rejects_unknown_account_with_same_message(client):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["message"] == "Invalid email or password."


def test_me_requires_authentication(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_me_returns_the_signed_in_user(signed_in):
    response = signed_in.get("/api/auth/me")

    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == "engineer@example.com"


def test_logout_clears_the_session(signed_in):
    assert signed_in.post("/api/auth/logout").status_code == 200
    assert signed_in.get("/api/auth/me").status_code == 401


def test_tampered_token_is_rejected(app, signed_in):
    cookie_name = app.config["BETTEROPS_CONFIG"].security.session_cookie_name
    signed_in._client.set_cookie(cookie_name, "not.a.valid.token", domain="localhost")

    assert signed_in.get("/api/auth/me").status_code == 401
