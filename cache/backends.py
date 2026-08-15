"""Cache backends.

Three implementations behind one narrow interface:

* `RedisBackend`  — the real one (ElastiCache in AWS, docker-compose locally).
* `MemoryBackend` — a per-process dictionary for tests and for local development without
  Redis. It implements the same TTL semantics so cache behaviour is genuinely exercised.
* `NullBackend`   — every read misses and every write is dropped.

The interface is deliberately small. Only these operations are used anywhere in the
application, which keeps the cache easy to reason about and easy to substitute.
"""

from __future__ import annotations

import fnmatch
import threading
import time
from typing import Callable, Protocol

import redis
from redis.exceptions import RedisError

from config import CACHE_BACKEND_MEMORY, CACHE_BACKEND_REDIS, Config


class CacheUnavailable(Exception):
    """The backend could not answer. Callers treat this as a miss, never as a failure."""


class CacheBackend(Protocol):
    """Operations the application needs from a cache."""

    name: str

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...

    def delete(self, *keys: str) -> int: ...

    def delete_matching(self, pattern: str) -> int: ...

    def increment(self, key: str, ttl_seconds: int) -> int: ...

    def ping(self) -> bool: ...


class RedisBackend:
    """Redis-backed cache.

    Every method translates a `RedisError` into `CacheUnavailable` so that no caller ever
    has to know which cache implementation is in use, or import a redis exception.
    """

    name = "redis"

    def __init__(self, url: str, socket_timeout_seconds: float) -> None:
        # A connection pool is required: each Flask worker and each Phase 9 investigation
        # worker makes many small calls, and reconnecting per call would dominate.
        self._client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=socket_timeout_seconds,
            socket_connect_timeout=socket_timeout_seconds,
            health_check_interval=30,
        )

    def get(self, key: str) -> str | None:
        try:
            return self._client.get(key)
        except RedisError as exc:
            raise CacheUnavailable(str(exc)) from exc

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            # Every cached value has a TTL. Nothing in this cache is allowed to live
            # forever, so a stale entry always ages out even if invalidation is missed.
            self._client.setex(key, ttl_seconds, value)
        except RedisError as exc:
            raise CacheUnavailable(str(exc)) from exc

    def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        try:
            return int(self._client.delete(*keys))
        except RedisError as exc:
            raise CacheUnavailable(str(exc)) from exc

    def delete_matching(self, pattern: str) -> int:
        try:
            # SCAN, not KEYS: KEYS blocks the whole server while it walks the keyspace.
            deleted = 0
            for key in self._client.scan_iter(match=pattern, count=200):
                deleted += int(self._client.delete(key))
            return deleted
        except RedisError as exc:
            raise CacheUnavailable(str(exc)) from exc

    def increment(self, key: str, ttl_seconds: int) -> int:
        try:
            pipeline = self._client.pipeline()
            pipeline.incr(key)
            # Refreshing the TTL on every hit would make a fixed window slide; setting it
            # unconditionally is safe here because the key name contains the window.
            pipeline.expire(key, ttl_seconds)
            count, _ = pipeline.execute()
            return int(count)
        except RedisError as exc:
            raise CacheUnavailable(str(exc)) from exc

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except RedisError:
            return False

    def close(self) -> None:
        try:
            self._client.close()
        except RedisError:
            pass


class MemoryBackend:
    """In-process cache with real TTL semantics.

    `clock` is swappable so expiry can be tested without sleeping.
    """

    name = "memory"

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[str, float]] = {}

    def _live_value(self, key: str) -> str | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at <= self.clock():
            del self._entries[key]
            return None
        return value

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._live_value(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        with self._lock:
            self._entries[key] = (value, self.clock() + ttl_seconds)

    def delete(self, *keys: str) -> int:
        with self._lock:
            return sum(1 for key in keys if self._entries.pop(key, None) is not None)

    def delete_matching(self, pattern: str) -> int:
        with self._lock:
            matched = [key for key in self._entries if fnmatch.fnmatchcase(key, pattern)]
            for key in matched:
                del self._entries[key]
            return len(matched)

    def increment(self, key: str, ttl_seconds: int) -> int:
        with self._lock:
            current = self._live_value(key)
            count = int(current) + 1 if current is not None else 1
            self._entries[key] = (str(count), self.clock() + ttl_seconds)
            return count

    def ping(self) -> bool:
        return True

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class NullBackend:
    """Caching turned off: reads miss, writes vanish, counters stay at zero.

    A zero from `increment` means "unknown", which makes the rate limiter fail open.
    """

    name = "disabled"

    def get(self, key: str) -> str | None:
        return None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        return None

    def delete(self, *keys: str) -> int:
        return 0

    def delete_matching(self, pattern: str) -> int:
        return 0

    def increment(self, key: str, ttl_seconds: int) -> int:
        return 0

    def ping(self) -> bool:
        return True


def build_backend(config: Config) -> CacheBackend:
    if config.cache.backend == CACHE_BACKEND_REDIS:
        return RedisBackend(config.cache.redis_url, config.cache.socket_timeout_seconds)
    if config.cache.backend == CACHE_BACKEND_MEMORY:
        return MemoryBackend()
    return NullBackend()
