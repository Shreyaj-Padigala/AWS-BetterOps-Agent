"""Structured logging: JSON shape, request context fields and redaction."""

from __future__ import annotations

import json
import logging

from logging_config import JsonFormatter


def _format(record_kwargs: dict, message: str = "hello") -> dict:
    record = logging.LogRecord(
        name="betterops.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for field, value in record_kwargs.items():
        setattr(record, field, value)
    return json.loads(JsonFormatter().format(record))


def test_json_log_has_the_standard_envelope():
    payload = _format({})

    assert payload["level"] == "INFO"
    assert payload["logger"] == "betterops.request"
    assert payload["message"] == "hello"
    assert payload["timestamp"].endswith("+00:00")


def test_extra_fields_become_top_level_keys():
    payload = _format(
        {
            "request_id": "abc123",
            "user_id": 7,
            "organization_id": 3,
            "duration_ms": 12.5,
            "status": 200,
        }
    )

    assert payload["request_id"] == "abc123"
    assert payload["organization_id"] == 3
    assert payload["duration_ms"] == 12.5


def test_sensitive_fields_are_redacted():
    payload = _format({"password": "hunter2", "access_token": "ghp_secret", "user_id": 7})

    assert payload["password"] == "[redacted]"
    assert payload["access_token"] == "[redacted]"
    assert payload["user_id"] == 7


def test_unserialisable_values_do_not_break_logging():
    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    payload = _format({"thing": Opaque()})

    assert payload["thing"] == "<opaque>"


def test_exceptions_are_included():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="betterops",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
        payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]


def test_request_logs_carry_the_request_id(app, caplog):
    client = app.test_client()

    with caplog.at_level(logging.INFO, logger="betterops.request"):
        response = client.get("/healthz")

    record = next(r for r in caplog.records if r.name == "betterops.request")
    assert record.request_id == response.headers["X-Request-Id"]
    assert record.status == 200
    assert record.path == "/healthz"
    assert record.duration_ms >= 0


def test_request_logs_carry_the_tenant_once_authenticated(signed_in, caplog):
    with caplog.at_level(logging.INFO, logger="betterops.request"):
        signed_in.get("/api/projects")

    record = next(r for r in caplog.records if r.name == "betterops.request")
    assert record.user_id == signed_in.user["id"]
    assert record.organization_id == signed_in.organization["id"]
