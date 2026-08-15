"""Incident reads served through the cache, and invalidated on write."""

from __future__ import annotations

from cache import cache_service, metrics, redis_client
from tests.test_cache import FailingBackend


def test_second_read_is_served_from_the_cache(signed_in):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])
    metrics.reset()

    first = signed_in.get(f"/api/incidents/{incident['id']}").get_json()
    second = signed_in.get(f"/api/incidents/{incident['id']}").get_json()

    assert first == second
    stats = metrics.snapshot()
    assert (stats.misses, stats.hits) == (1, 1)


def test_update_invalidates_the_cached_incident(signed_in):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])

    # Populate the cache, then change the record.
    assert signed_in.get(f"/api/incidents/{incident['id']}").get_json()["status"] == "OPEN"
    signed_in.put(f"/api/incidents/{incident['id']}", {"status": "INVESTIGATING"})

    refreshed = signed_in.get(f"/api/incidents/{incident['id']}").get_json()

    assert refreshed["status"] == "INVESTIGATING"


def test_cache_entry_is_removed_on_update(signed_in):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])
    organization_id = signed_in.organization["id"]
    key = cache_service.incident_key(organization_id, incident["id"])

    signed_in.get(f"/api/incidents/{incident['id']}")
    assert cache_service.get(key) is not None

    signed_in.put(f"/api/incidents/{incident['id']}", {"severity": "SEV-1"})

    assert cache_service.get(key) is None


def test_a_missing_incident_is_never_cached(signed_in):
    assert signed_in.get("/api/incidents/4242").status_code == 404
    # A 404 must not be stored, or creating incident 4242 later would keep 404ing.
    assert cache_service.get(cache_service.incident_key(signed_in.organization["id"], 4242)) is None


def test_cached_incidents_are_not_visible_to_another_organization(signed_in, other_org):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])

    # Warm the cache for the owning organization.
    assert signed_in.get(f"/api/incidents/{incident['id']}").status_code == 200

    assert other_org.get(f"/api/incidents/{incident['id']}").status_code == 404


def test_incident_reads_still_work_when_the_cache_is_down(signed_in):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])

    redis_client.set_backend(FailingBackend())

    response = signed_in.get(f"/api/incidents/{incident['id']}")

    assert response.status_code == 200
    assert response.get_json()["id"] == incident["id"]


def test_cache_stats_endpoint_reports_hit_rate(signed_in):
    project = signed_in.create_project()
    incident = signed_in.create_incident(project["id"])
    metrics.reset()

    signed_in.get(f"/api/incidents/{incident['id']}")
    signed_in.get(f"/api/incidents/{incident['id']}")

    body = signed_in.get("/api/system/cache").get_json()

    assert body["counters"]["hits"] == 1
    assert body["counters"]["misses"] == 1
    assert body["counters"]["hit_rate"] == 0.5
    assert body["cache"]["backend"] == "memory"


def test_cache_stats_endpoint_requires_authentication(client):
    assert client.get("/api/system/cache").status_code == 401
