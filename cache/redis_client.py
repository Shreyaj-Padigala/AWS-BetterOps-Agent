"""Process-wide cache backend.

Built once per process and shared, mirroring `database/db.py`: the Flask web tasks and
the Phase 9 investigation workers both go through this module, so there is one place
where the cache connection is configured.
"""

from __future__ import annotations

from cache.backends import CacheBackend, MemoryBackend, build_backend
from config import get_config

_backend: CacheBackend | None = None


def get_backend() -> CacheBackend:
    global _backend
    if _backend is None:
        _backend = build_backend(get_config())
    return _backend


def reset_backend() -> None:
    """Drop the backend so the next call rebuilds it. Used by tests."""
    global _backend
    close = getattr(_backend, "close", None)
    if close is not None:
        close()
    _backend = None


def set_backend(backend: CacheBackend) -> None:
    """Install a specific backend. Used by tests to simulate an outage."""
    global _backend
    _backend = backend


def health() -> dict[str, str]:
    """Backend name and reachability, for `/healthz`.

    A cache outage is reported but does not make the application unhealthy: requests
    still succeed, just without cache hits.
    """
    backend = get_backend()
    return {"backend": backend.name, "status": "ok" if backend.ping() else "unavailable"}


def clear_memory_backend() -> None:
    """Empty an in-memory backend between tests. No-op for other backends."""
    backend = get_backend()
    if isinstance(backend, MemoryBackend):
        backend.clear()
