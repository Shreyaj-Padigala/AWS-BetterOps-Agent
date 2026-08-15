"""The Redis backend, exercised against an in-process Redis server.

`fakeredis` speaks the real protocol to the real `redis-py` client, so these tests cover
the parts the in-memory backend cannot: `SETEX` TTLs, `SCAN`-based pattern deletion, the
`INCR`/`EXPIRE` pipeline, `decode_responses`, and the translation of `RedisError` into
`CacheUnavailable`.
"""

from __future__ import annotations

import fakeredis
import pytest
import redis
from redis.exceptions import ConnectionError as RedisConnectionError

from cache.backends import CacheUnavailable, RedisBackend


@pytest.fixture()
def backend(monkeypatch):
    server = fakeredis.FakeServer()

    def fake_from_url(url, **kwargs):
        return fakeredis.FakeRedis(server=server, **kwargs)

    monkeypatch.setattr(redis.Redis, "from_url", fake_from_url)
    return RedisBackend("redis://localhost:6379/0", socket_timeout_seconds=0.5)


def test_set_and_get_round_trip(backend):
    backend.set("k1", '{"value": 1}', ttl_seconds=60)

    # decode_responses must be on, or every read would come back as bytes.
    assert backend.get("k1") == '{"value": 1}'


def test_missing_key_returns_none(backend):
    assert backend.get("absent") is None


def test_values_are_stored_with_a_ttl(backend):
    backend.set("k1", "value", ttl_seconds=45)

    ttl = backend._client.ttl("k1")

    assert 0 < ttl <= 45, "cached values must always expire on their own"


def test_delete_reports_how_many_keys_were_removed(backend):
    backend.set("k1", "a", 60)
    backend.set("k2", "b", 60)

    assert backend.delete("k1", "k2", "never-existed") == 2
    assert backend.get("k1") is None


def test_delete_matching_removes_only_the_matched_namespace(backend):
    backend.set("betterops:v1:incident:1:10", "a", 60)
    backend.set("betterops:v1:incident:1:11", "b", 60)
    backend.set("betterops:v1:project:1:5", "c", 60)

    removed = backend.delete_matching("betterops:v1:incident:*")

    assert removed == 2
    assert backend.get("betterops:v1:project:1:5") == "c"


def test_increment_counts_and_sets_an_expiry(backend):
    assert backend.increment("counter", ttl_seconds=60) == 1
    assert backend.increment("counter", ttl_seconds=60) == 2
    # Without the expiry a rate-limit window would never fall out of the keyspace.
    assert backend._client.ttl("counter") > 0


def test_ping_reports_reachability(backend):
    assert backend.ping() is True


def test_connection_errors_become_cache_unavailable(backend, monkeypatch):
    def boom(*args, **kwargs):
        raise RedisConnectionError("connection refused")

    monkeypatch.setattr(backend._client, "get", boom)

    # Callers must never have to catch a redis-specific exception.
    with pytest.raises(CacheUnavailable):
        backend.get("k1")


def test_unreachable_server_pings_false(monkeypatch):
    server = fakeredis.FakeServer()
    # Simulates the server being down: every command raises a connection error.
    server.connected = False

    monkeypatch.setattr(
        redis.Redis, "from_url", lambda url, **kwargs: fakeredis.FakeRedis(server=server, **kwargs)
    )
    backend = RedisBackend("redis://localhost:6379/0", socket_timeout_seconds=0.5)

    assert backend.ping() is False


def test_commands_against_a_down_server_raise_cache_unavailable(monkeypatch):
    server = fakeredis.FakeServer()
    server.connected = False

    monkeypatch.setattr(
        redis.Redis, "from_url", lambda url, **kwargs: fakeredis.FakeRedis(server=server, **kwargs)
    )
    backend = RedisBackend("redis://localhost:6379/0", socket_timeout_seconds=0.5)

    for operation in (
        lambda: backend.get("k"),
        lambda: backend.set("k", "v", 60),
        lambda: backend.delete("k"),
        lambda: backend.delete_matching("k:*"),
        lambda: backend.increment("k", 60),
    ):
        with pytest.raises(CacheUnavailable):
            operation()
