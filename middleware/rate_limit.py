"""Rate limiting.

A fixed window per identity per route class, counted in Redis so the limit holds across
every ECS task rather than per process.

The window start is part of the key (`…:ratelimit:api:user_7:29331482`), so the counter
resets by expiring rather than by anyone resetting it, and a concurrent increment can
never extend a window that is already running.

Two deliberate choices:

* **Identity.** Authenticated requests are limited per user, because that is the unit
  that consumes agent work and Bedrock tokens. Unauthenticated requests fall back to the
  client address.
* **Fail open.** If Redis is unreachable the request is allowed. Rate limiting protects
  cost and fairness; refusing every request during a cache outage would turn a degraded
  dependency into an outage of our own. The cache error counter records it either way.

A fixed window permits a burst of up to 2x the limit across a window boundary. That is
acceptable for the limits here; the investigation endpoint added in Phase 9 gets a
distributed lock as well, which is the control that actually matters there.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from flask import Flask, request

from cache import cache_service
from config import get_config
from errors import RateLimitError
from middleware.auth_middleware import optional_context

logger = logging.getLogger("betterops.ratelimit")

WINDOW_SECONDS = 60
# Counters outlive their window slightly so a clock skew between tasks cannot drop one.
_KEY_TTL_SECONDS = WINDOW_SECONDS * 2


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit_per_minute: int
    # Auth endpoints are limited by client address: there is no user yet, and the point
    # is to slow down credential guessing against *any* account.
    per_client_address: bool = False


def _rule_for_request() -> RateLimitRule | None:
    """The rule that applies to the current request, or None if it is not limited."""
    config = get_config()
    path = request.path

    if not path.startswith("/api/"):
        # Pages and static assets are cheap and are not rate limited.
        return None

    if path.startswith("/api/auth/") and request.method == "POST":
        return RateLimitRule(
            "auth", config.cache.rate_limit_auth_per_minute, per_client_address=True
        )

    return RateLimitRule("api", config.cache.rate_limit_api_per_minute)


def _identity(rule: RateLimitRule) -> str:
    if not rule.per_client_address:
        # `optional_context` returns None for anonymous or invalid sessions, and caches
        # the resolved context on the request so `login_required` does not repeat the
        # lookup a moment later.
        context = optional_context()
        if context is not None:
            return f"user_{context.user.id}"
    return f"ip_{request.remote_addr or 'unknown'}"


def _window_start(now: float) -> int:
    return int(now // WINDOW_SECONDS) * WINDOW_SECONDS


def check(rule: RateLimitRule, identity: str, now: float | None = None) -> None:
    """Count this request and raise `RateLimitError` if the window is exhausted."""
    now = time.time() if now is None else now
    window_start = _window_start(now)
    key = cache_service.key(cache_service.NS_RATE_LIMIT, rule.name, identity, window_start)

    count = cache_service.increment(key, _KEY_TTL_SECONDS)
    if count == 0:
        # Backend unavailable: fail open (see module docstring).
        return

    if count > rule.limit_per_minute:
        retry_after = max(1, int(window_start + WINDOW_SECONDS - now))
        logger.warning(
            "Rate limit exceeded",
            extra={"rule": rule.name, "identity": identity, "count": count},
        )
        raise RateLimitError(
            f"Rate limit of {rule.limit_per_minute} requests per minute exceeded.",
            retry_after=retry_after,
        )


def init_app(app: Flask) -> None:
    @app.before_request
    def _enforce_rate_limit() -> None:
        config = get_config()
        if not config.cache.rate_limit_enabled:
            return
        rule = _rule_for_request()
        if rule is None:
            return
        check(rule, _identity(rule))
