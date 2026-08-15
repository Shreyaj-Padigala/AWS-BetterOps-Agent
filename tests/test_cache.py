"""Cache keys, cache-aside semantics, invalidation and graceful degradation."""

from __future__ import annotations

import json

import pytest

from cache import cache_service, metrics, redis_client
from cache.backends import CacheUnavailable, MemoryBackend


class FailingBackend:
    """Stands in for an unreachable Redis: every operation raises."""

    name = "failing"

    def _fail(self, *args, **kwargs):
        raise CacheUnavailable("connection refused")

    get = set = delete = delete_matching = increment = _fail

    def ping(self) -> bool:
        return False


@pytest.fixture()
def cache(app):
    """A fresh in-memory backend with a controllable clock."""
    backend = MemoryBackend()
    redis_client.set_backend(backend)
    metrics.reset()
    return backend


# --- Keys -------------------------------------------------------------------


def test_key_is_namespaced_and_versioned():
    assert cache_service.key("incident", 7, 42) == "betterops:v1:incident:7:42"


def test_key_parts_cannot_inject_separators():
    # A value containing ':' must not be able to masquerade as extra key segments.
    assert cache_service.key("incident", "1:2") == "betterops:v1:incident:1_2"


def test_long_key_parts_are_hashed_not_truncated():
    first = cache_service.key("rag", "q" * 200 + "a")
    second = cache_service.key("rag", "q" * 200 + "b")

    assert first != second
    assert len(first) < 120


def test_incident_key_includes_the_organization():
    # The tenant is part of the key itself, so a cached payload cannot be served to the
    # wrong organization even if ids were guessed.
    assert cache_service.incident_key(3, 9) != cache_service.incident_key(4, 9)


# --- Cache-aside ------------------------------------------------------------


def test_miss_then_hit(cache):
    calls = []

    def loader():
        calls.append(1)
        return {"value": "loaded"}

    first = cache_service.get_or_set("k1", 60, loader)
    second = cache_service.get_or_set("k1", 60, loader)

    assert first == second == {"value": "loaded"}
    assert len(calls) == 1, "the loader must not run on a hit"

    stats = metrics.snapshot()
    assert (stats.hits, stats.misses) == (1, 1)
    assert stats.hit_rate == 0.5


def test_values_expire_after_their_ttl(cache):
    now = 1_000.0
    cache.clock = lambda: now

    cache_service.set("k1", {"value": 1}, ttl_seconds=30)
    assert cache_service.get("k1") == {"value": 1}

    now = 1_031.0
    assert cache_service.get("k1") is None


def test_none_is_not_cached(cache):
    # None is indistinguishable from a miss, so storing it would be a permanent miss
    # that also hides the real value.
    cache_service.set("k1", None, ttl_seconds=60)

    assert cache_service.get("k1") is None


def test_loader_errors_are_not_cached(cache):
    def failing_loader():
        raise RuntimeError("database down")

    with pytest.raises(RuntimeError):
        cache_service.get_or_set("k1", 60, failing_loader)

    assert cache_service.get("k1") is None


def test_undecodable_entry_is_treated_as_a_miss(cache):
    # Simulates a value written by an older, incompatible version of the code.
    cache.set("k1", "not json", 60)

    assert cache_service.get("k1") is None
    assert cache.get("k1") is None, "the bad entry should have been dropped"


def test_invalidate_removes_a_key(cache):
    cache_service.set("k1", {"value": 1}, ttl_seconds=60)

    assert cache_service.invalidate("k1") == 1
    assert cache_service.get("k1") is None
    assert metrics.snapshot().invalidations == 1


def test_invalidate_pattern_removes_a_whole_namespace(cache):
    cache_service.set(cache_service.key("incident", 1, 10), {"id": 10}, 60)
    cache_service.set(cache_service.key("incident", 1, 11), {"id": 11}, 60)
    cache_service.set(cache_service.key("project", 1, 5), {"id": 5}, 60)

    removed = cache_service.invalidate_pattern(cache_service.namespace_pattern("incident"))

    assert removed == 2
    assert cache_service.get(cache_service.key("project", 1, 5)) == {"id": 5}


def test_stored_values_are_json(cache):
    cache_service.set("k1", {"value": 1}, ttl_seconds=60)

    assert json.loads(cache.get("k1")) == {"value": 1}


# --- Degradation ------------------------------------------------------------


def test_reads_fall_back_to_the_loader_when_the_backend_is_down(app):
    redis_client.set_backend(FailingBackend())
    metrics.reset()

    result = cache_service.get_or_set("k1", 60, lambda: {"value": "from source"})

    assert result == {"value": "from source"}
    stats = metrics.snapshot()
    assert stats.errors >= 1
    assert stats.hits == 0


def test_invalidation_is_survivable_when_the_backend_is_down(app):
    redis_client.set_backend(FailingBackend())

    assert cache_service.invalidate("k1") == 0
    assert cache_service.invalidate_pattern("betterops:v1:incident:*") == 0


def test_increment_returns_zero_when_the_backend_is_down(app):
    redis_client.set_backend(FailingBackend())

    # Zero means "unknown", which is what makes the rate limiter fail open.
    assert cache_service.increment("k1", 60) == 0


def test_disabled_backend_never_stores_anything(monkeypatch, app_factory):
    monkeypatch.setenv("CACHE_BACKEND", "disabled")
    flask_app = app_factory()

    with flask_app.app_context():
        cache_service.set("k1", {"value": 1}, ttl_seconds=60)
        assert cache_service.get("k1") is None
