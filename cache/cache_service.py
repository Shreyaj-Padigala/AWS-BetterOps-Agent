"""Cache-aside helpers.

Read path:  look in the cache → on a miss call the loader → store the result → return it.
Write path: update PostgreSQL, then delete the affected keys.

Two rules hold everywhere in this module:

1. **A cache failure is never a request failure.** If the backend is unreachable or slow,
   the lookup is counted as an error and the loader runs. The user sees a slower
   response, not a 500.
2. **Every value has a TTL.** Even if an invalidation is missed, a stale entry ages out.

Keys are `betterops:{version}:{namespace}:{parts...}`. The version lets an incompatible
change to a cached shape invalidate everything at once, and the namespace lets a whole
family of keys be dropped with one pattern delete.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Callable

from cache import metrics
from cache.backends import CacheUnavailable
from cache.redis_client import get_backend

logger = logging.getLogger("betterops.cache")

KEY_PREFIX = "betterops"
KEY_VERSION = "v1"

# Namespaces are added by the phase that needs them.
NS_INCIDENT = "incident"
NS_RATE_LIMIT = "ratelimit"

# A backend outage would otherwise log on every single request.
_OUTAGE_LOG_INTERVAL_SECONDS = 30.0
_last_outage_log_at = 0.0


def _sanitize(part: Any) -> str:
    """Make a key part safe: no separators, bounded length.

    Long values (a search query, a file path) are hashed rather than truncated, so two
    different inputs cannot collide onto the same key.
    """
    text = str(part).strip().replace(":", "_").replace(" ", "_")
    return text if len(text) <= 64 else hash_part(text)


def hash_part(text: str) -> str:
    """Stable short digest, for key parts that are too long or unbounded."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def key(namespace: str, *parts: Any) -> str:
    return ":".join([KEY_PREFIX, KEY_VERSION, namespace, *(_sanitize(p) for p in parts)])


def namespace_pattern(namespace: str, *parts: Any) -> str:
    """Pattern matching every key under a namespace, for bulk invalidation."""
    if parts:
        return key(namespace, *parts) + ":*"
    return f"{KEY_PREFIX}:{KEY_VERSION}:{namespace}:*"


def _log_outage(operation: str, error: Exception) -> None:
    global _last_outage_log_at
    now = time.monotonic()
    if now - _last_outage_log_at < _OUTAGE_LOG_INTERVAL_SECONDS:
        return
    _last_outage_log_at = now
    logger.warning(
        "Cache unavailable during %s; serving from the source instead: %s", operation, error
    )


def get(cache_key: str) -> Any | None:
    """Read a cached value, or None on a miss, a decode failure, or an outage."""
    backend = get_backend()
    try:
        raw = backend.get(cache_key)
    except CacheUnavailable as exc:
        metrics.record_error()
        _log_outage("get", exc)
        return None

    if raw is None:
        metrics.record_miss()
        return None

    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        # A value written by an older, incompatible version of the code. Drop it and
        # treat the lookup as a miss rather than failing the request.
        logger.warning("Discarding undecodable cache entry %s", cache_key)
        invalidate(cache_key)
        metrics.record_miss()
        return None

    metrics.record_hit()
    return value


def set(cache_key: str, value: Any, ttl_seconds: int) -> None:
    """Store a value. `None` is not cached, because it is indistinguishable from a miss."""
    if value is None:
        return
    try:
        get_backend().set(cache_key, json.dumps(value, default=str), ttl_seconds)
    except CacheUnavailable as exc:
        metrics.record_error()
        _log_outage("set", exc)


def get_or_set(cache_key: str, ttl_seconds: int, loader: Callable[[], Any]) -> Any:
    """The cache-aside read path.

    The loader is only called on a miss, and any exception it raises propagates
    untouched — a failed load must not be cached.
    """
    cached = get(cache_key)
    if cached is not None:
        return cached

    value = loader()
    set(cache_key, value, ttl_seconds)
    return value


def invalidate(*cache_keys: str) -> int:
    """Delete specific keys. Called after the source of truth changes."""
    if not cache_keys:
        return 0
    try:
        deleted = get_backend().delete(*cache_keys)
    except CacheUnavailable as exc:
        metrics.record_error()
        _log_outage("delete", exc)
        return 0
    metrics.record_invalidation(deleted)
    return deleted


def invalidate_pattern(pattern: str) -> int:
    """Delete every key matching a pattern, e.g. all of one project's cached documents."""
    try:
        deleted = get_backend().delete_matching(pattern)
    except CacheUnavailable as exc:
        metrics.record_error()
        _log_outage("delete_matching", exc)
        return 0
    metrics.record_invalidation(deleted)
    return deleted


def increment(cache_key: str, ttl_seconds: int) -> int:
    """Counter increment for the rate limiter. Returns 0 when the backend is unavailable."""
    try:
        return get_backend().increment(cache_key, ttl_seconds)
    except CacheUnavailable as exc:
        metrics.record_error()
        _log_outage("increment", exc)
        return 0


def incident_key(organization_id: int, incident_id: int) -> str:
    """Cached incident payloads are keyed by organization as well as id.

    The organization is part of the key, not just of the query behind it, so a cached
    entry can never be served to the wrong tenant.
    """
    return key(NS_INCIDENT, organization_id, incident_id)
