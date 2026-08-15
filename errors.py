"""Application error types and the single JSON error contract.

Services raise these; one Flask error handler turns them into responses. Route handlers
therefore contain no try/except for control flow, and every client-visible failure has
the same shape:

    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Base class for all errors that are safe to show a client."""

    status_code = 500
    code = "internal_error"

    def __init__(
        self,
        message: str = "Something went wrong.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ValidationError(ApiError):
    status_code = 400
    code = "validation_error"

    def __init__(
        self,
        message: str = "The request body is invalid.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)


class AuthError(ApiError):
    status_code = 401
    code = "unauthorized"

    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(message)


class ForbiddenError(ApiError):
    status_code = 403
    code = "forbidden"

    def __init__(self, message: str = "You do not have access to this resource.") -> None:
        super().__init__(message)


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"

    def __init__(self, message: str = "Resource not found.") -> None:
        super().__init__(message)


class ConflictError(ApiError):
    status_code = 409
    code = "conflict"

    def __init__(self, message: str = "That resource already exists.") -> None:
        super().__init__(message)


class RateLimitError(ApiError):
    """Raised by the Phase 2 rate limiter."""

    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str = "Too many requests.", retry_after: int = 60) -> None:
        super().__init__(message, {"retry_after": retry_after})
        self.retry_after = retry_after
