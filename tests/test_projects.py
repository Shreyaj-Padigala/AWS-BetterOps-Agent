"""Project creation, listing, retrieval and updates."""

from __future__ import annotations


def test_create_project(signed_in):
    project = signed_in.create_project(key="checkout", name="Checkout Platform")

    # Keys are normalised to uppercase so they read as identifiers everywhere.
    assert project["key"] == "CHECKOUT"
    assert project["open_incident_count"] == 0


def test_create_project_rejects_duplicate_key(signed_in):
    signed_in.create_project(key="CHECKOUT")
    response = signed_in.post("/api/projects", {"key": "CHECKOUT", "name": "Another"})

    assert response.status_code == 409


def test_create_project_rejects_invalid_key(signed_in):
    response = signed_in.post("/api/projects", {"key": "9bad key!", "name": "Bad"})

    assert response.status_code == 400
    assert "key" in response.get_json()["error"]["details"]


def test_create_project_rejects_non_http_repository_url(signed_in):
    response = signed_in.post(
        "/api/projects",
        {"key": "REPO", "name": "Repo", "repository_url": "git@github.com:acme/checkout.git"},
    )

    assert response.status_code == 400
    assert "repository_url" in response.get_json()["error"]["details"]


def test_list_projects_includes_open_incident_counts(signed_in):
    project = signed_in.create_project()
    signed_in.create_incident(project["id"])
    signed_in.create_incident(project["id"], title="Second problem")

    items = signed_in.get("/api/projects").get_json()["items"]

    assert len(items) == 1
    assert items[0]["open_incident_count"] == 2


def test_resolved_incidents_do_not_count_as_open(signed_in):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])
    signed_in.put(f"/api/incidents/{incident['id']}", {"status": "RESOLVED"})

    items = signed_in.get("/api/projects").get_json()["items"]

    assert items[0]["open_incident_count"] == 0


def test_get_unknown_project_returns_404(signed_in):
    assert signed_in.get("/api/projects/9999").status_code == 404


def test_update_project_applies_only_supplied_fields(signed_in):
    project = signed_in.create_project(description="Original description")

    response = signed_in.put(f"/api/projects/{project['id']}", {"name": "Renamed"})

    assert response.status_code == 200
    body = response.get_json()
    assert body["name"] == "Renamed"
    # Omitted fields must survive a partial update.
    assert body["description"] == "Original description"


def test_projects_require_authentication(client):
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/projects", json={"key": "X", "name": "Y"}).status_code == 401
