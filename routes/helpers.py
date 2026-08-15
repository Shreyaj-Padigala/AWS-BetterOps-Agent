"""Small helpers shared by route modules."""

from __future__ import annotations

from typing import Any, TypeVar

from flask import request
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from errors import ValidationError

TModel = TypeVar("TModel", bound=BaseModel)


def parse_body(model: type[TModel]) -> TModel:
    """Validate the JSON body against a Pydantic model.

    Pydantic's field errors are flattened into the `details` object of the standard error
    response so the frontend can highlight individual inputs.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValidationError("A JSON request body is required.")
    if not isinstance(payload, dict):
        raise ValidationError("The request body must be a JSON object.")

    try:
        return model.model_validate(payload)
    except PydanticValidationError as exc:
        raise ValidationError("The request body is invalid.", _field_errors(exc)) from exc


def _field_errors(exc: PydanticValidationError) -> dict[str, str]:
    details: dict[str, str] = {}
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "body"
        # Pydantic prefixes messages with "Value error, "; the client does not need it.
        message = error["msg"].removeprefix("Value error, ")
        details.setdefault(location, message)
    return details


def query_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationError(f"Query parameter '{name}' must be an integer.") from exc
    if value < minimum or value > maximum:
        raise ValidationError(
            f"Query parameter '{name}' must be between {minimum} and {maximum}."
        )
    return value


def paginated(items: list[Any], total: int, limit: int, offset: int) -> dict[str, Any]:
    return {
        "items": items,
        "pagination": {"total": total, "limit": limit, "offset": offset},
    }
