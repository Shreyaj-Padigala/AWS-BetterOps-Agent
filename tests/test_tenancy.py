"""Multi-tenancy isolation.

Every tenant-scoped query filters on `organization_id`, so another organization's records
must be indistinguishable from records that do not exist — 404, never 403, because a 403
would confirm the id is real.
"""

from __future__ import annotations


def test_projects_are_not_listed_across_organizations(signed_in, other_org):
    signed_in.create_project(key="CHECKOUT")

    items = other_org.get("/api/projects").get_json()["items"]

    assert items == []


def test_another_organizations_project_is_not_readable(signed_in, other_org):
    project = signed_in.create_project()

    response = other_org.get(f"/api/projects/{project['id']}")

    assert response.status_code == 404


def test_another_organizations_project_is_not_writable(signed_in, other_org):
    project = signed_in.create_project()

    response = other_org.put(f"/api/projects/{project['id']}", {"name": "Hijacked"})

    assert response.status_code == 404


def test_incidents_cannot_be_created_in_another_organizations_project(signed_in, other_org):
    project = signed_in.create_project()

    response = other_org.post(f"/api/projects/{project['id']}/incidents", {"title": "Injected"})

    assert response.status_code == 404


def test_another_organizations_incident_is_not_readable(signed_in, other_org):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])

    assert other_org.get(f"/api/incidents/{incident['id']}").status_code == 404


def test_another_organizations_incident_is_not_writable(signed_in, other_org):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])

    response = other_org.put(f"/api/incidents/{incident['id']}", {"status": "CLOSED"})

    assert response.status_code == 404


def test_incident_lists_are_scoped_to_the_organization(signed_in, other_org):
    project = signed_in.create_project()
    signed_in.create_incident(project["id"])

    assert other_org.get("/api/incidents").get_json()["items"] == []


def test_dashboard_counts_are_scoped_to_the_organization(signed_in, other_org):
    project = signed_in.create_project()
    signed_in.create_incident(project["id"])

    summary = other_org.get("/api/dashboard").get_json()

    assert summary["total_incidents"] == 0
    assert summary["project_count"] == 0
