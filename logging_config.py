"""Logging setup.

Two formats, one configuration point:

* `text` — readable in a terminal, the default in development.
* `json` — one object per line, the default everywhere CloudWatch Logs Insights reads
  them. Structured fields (`request_id`, `organization_id`, `investigation_id`, `agent`,
  `tool`, `duration_ms`) become queryable columns instead of substrings to grep.

Nothing here ever serialises a request body, headers or cookies. Passwords, tokens, AWS
credentials and database passwords must not reach a log line, so only the explicitly
listed fields are emitted.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from config import LOG_FORMAT_JSON, Config

# Attributes every LogRecord carries. Anything else on a record came from `extra=` and is
# therefore a structured field we want in the output.
_STANDARD_RECORD_FIELDS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "message", "module", "msecs", "msg", "name",
        "pathname", "process", "processName", "relativeCreated", "stack_info",
        "taskName", "thread", "threadName",
    }
)

# Field names that must never appear in a log line even if something passes them in.
_FORBIDDEN_FIELDS = frozenset(
    {
        "password", "password_hash", "token", "access_token", "secret", "secret_key",
        "authorization", "cookie", "api_key", "private_key", "credentials",
    }
)


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field, value in record.__dict__.items():
            if field in _STANDARD_RECORD_FIELDS or field.startswith("_"):
                continue
            if field.lower() in _FORBIDDEN_FIELDS:
                payload[field] = "[redacted]"
                continue
            payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # `default=str` keeps a stray datetime or UUID from turning a log call into an
        # exception inside the logging system.
        return json.dumps(payload, default=str)


# Marks the handler this module owns, so repeated configuration replaces our handler
# without discarding one somebody else attached (a test harness, gunicorn, a debugger).
_OWNED_HANDLER_FLAG = "_betterops_owned"


def configure_logging(config: Config) -> None:
    """Install the root handler. Safe to call more than once."""
    if config.log_format == LOG_FORMAT_JSON:
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    setattr(handler, _OWNED_HANDLER_FLAG, True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, config.log_level, logging.INFO))
    for existing in list(root.handlers):
        if getattr(existing, _OWNED_HANDLER_FLAG, False):
            root.removeHandler(existing)
    root.addHandler(handler)
