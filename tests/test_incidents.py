"""Incident creation, listing, filtering, paging and status transitions."""

from __future__ import annotations


def test_create_incident_defaults(signed_in):
    project = signed_in.create_project(primary_service="checkout-service")
    incident = signed_in.create_incident(project["id"])

    assert incident["reference"] == f"INC-{incident['id']}"
    assert incident["status"] == "OPEN"
    assert incident["severity"] == "SEV-3"
    assert incident["source"] == "manual"
    # With no service given, the project's primary service seeds triage.
    assert incident["affected_service"] == "checkout-service"
    assert incident["started_at"] is not None


def test_create_incident_accepts_explicit_start_time(signed_in):
    project = signed_in.create_project()
    incident = signed_in.create_incident(
        project["id"], severity="SEV-2", started_at="2026-08-14T14:19:00+00:00"
    )

    assert incident["severity"] == "SEV-2"
    assert incident["started_at"].startswith("2026-08-14T14:19:00")


def test_create_incident_rejects_unknown_severity(signed_in):
    project = signed_in.create_project()
    response = signed_in.post(
        f"/api/projects/{project['id']}/incidents",
        {"title": "Bad severity", "severity": "SEV-9"},
    )

    assert response.status_code == 400
    assert "severity" in response.get_json()["error"]["details"]


def test_create_incident_rejects_empty_title(signed_in):
    project = signed_in.create_project()
    response = signed_in.post(f"/api/projects/{project['id']}/incidents", {"title": "   "})

    assert response.status_code == 400


def test_create_incident_for_unknown_project_returns_404(signed_in):
    response = signed_in.post("/api/projects/4242/incidents", {"title": "Nowhere"})

    assert response.status_code == 404


def test_list_incidents_is_newest_first(signed_in):
    project = signed_in.create_project()
    signed_in.create_incident(project["id"], title="Older", started_at="2026-08-01T10:00:00+00:00")
    signed_in.create_incident(project["id"], title="Newer", started_at="2026-08-10T10:00:00+00:00")

    items = signed_in.get("/api/incidents").get_json()["items"]

    assert [item["title"] for item in items] == ["Newer", "Older"]


def test_list_incidents_filters_by_status(signed_in):
    project = signed_in.create_project()
    first = signed_in.create_incident(project["id"], title="Will resolve")
    signed_in.create_incident(project["id"], title="Stays open")
    signed_in.put(f"/api/incidents/{first['id']}", {"status": "RESOLVED"})

    open_only = signed_in.get("/api/incidents?status=OPEN_ONLY").get_json()
    resolved = signed_in.get("/api/incidents?status=RESOLVED").get_json()

    assert [item["title"] for item in open_only["items"]] == ["Stays open"]
    assert [item["title"] for item in resolved["items"]] == ["Will resolve"]


def test_list_incidents_rejects_unknown_status_filter(signed_in):
    response = signed_in.get("/api/incidents?status=NOT_A_STATUS")

    assert response.status_code == 400


def test_list_incidents_pagination_reports_total(signed_in):
    project = signed_in.create_project()
    for index in range(3):
        signed_in.create_incident(project["id"], title=f"Incident {index}")

    page = signed_in.get("/api/incidents?limit=2&offset=0").get_json()

    assert len(page["items"]) == 2
    assert page["pagination"] == {"total": 3, "limit": 2, "offset": 0}


def test_list_incidents_rejects_oversized_limit(signed_in):
    response = signed_in.get("/api/incidents?limit=5000")

    assert response.status_code == 400


def test_project_scoped_listing_excludes_other_projects(signed_in):
    first = signed_in.create_project(key="CHECKOUT")
    second = signed_in.create_project(key="BILLING", name="Billing")
    signed_in.create_incident(first["id"], title="Checkout problem")
    signed_in.create_incident(second["id"], title="Billing problem")

    items = signed_in.get(f"/api/projects/{first['id']}/incidents").get_json()["items"]

    assert [item["title"] for item in items] == ["Checkout problem"]


def test_resolving_an_incident_sets_resolved_at(signed_in):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])

    resolved = signed_in.put(f"/api/incidents/{incident['id']}", {"status": "RESOLVED"}).get_json()

    assert resolved["status"] == "RESOLVED"
    assert resolved["resolved_at"] is not None


def test_reopening_an_incident_clears_resolved_at(signed_in):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])
    signed_in.put(f"/api/incidents/{incident['id']}", {"status": "RESOLVED"})

    reopened = signed_in.put(
        f"/api/incidents/{incident['id']}", {"status": "INVESTIGATING"}
    ).get_json()

    assert reopened["resolved_at"] is None


def test_update_incident_rejects_unknown_status(signed_in):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])

    response = signed_in.put(f"/api/incidents/{incident['id']}", {"status": "PROBABLY_FINE"})

    assert response.status_code == 400


def test_get_unknown_incident_returns_404(signed_in):
    assert signed_in.get("/api/incidents/9999").status_code == 404


def test_dashboard_summary(signed_in):
    project = signed_in.create_project()
    first = signed_in.create_incident(project["id"], title="Open one")
    signed_in.create_incident(project["id"], title="Will close")
    signed_in.put(f"/api/incidents/{first['id']}", {"status": "CLOSED"})

    summary = signed_in.get("/api/dashboard").get_json()

    assert summary["total_incidents"] == 2
    assert summary["open_incidents"] == 1
    assert summary["project_count"] == 1
    assert len(summary["recent_incidents"]) == 2
