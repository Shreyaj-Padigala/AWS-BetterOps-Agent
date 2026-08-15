"""Request schemas for incidents."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from constants import INCIDENT_SEVERITIES, INCIDENT_STATUSES, SEV3


def _as_utc(value: datetime | None) -> datetime | None:
    """Treat a naive timestamp as UTC so every stored value is comparable."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class CreateIncidentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=20000)
    severity: str = SEV3
    affected_service: str | None = Field(default=None, max_length=120)
    # When the problem began in production. Defaults to now if the reporter does not
    # know; agents correlate deployments against this value, not against created_at.
    started_at: datetime | None = None

    @field_validator("severity")
    @classmethod
    def severity_is_known(cls, value: str) -> str:
        value = value.upper()
        if value not in INCIDENT_SEVERITIES:
            raise ValueError(f"Severity must be one of {', '.join(INCIDENT_SEVERITIES)}.")
        return value

    @field_validator("started_at")
    @classmethod
    def started_at_is_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class UpdateIncidentRequest(BaseModel):
    """All fields optional — only supplied fields are applied."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=20000)
    severity: str | None = None
    status: str | None = None
    affected_service: str | None = Field(default=None, max_length=120)
    started_at: datetime | None = None

    @field_validator("severity")
    @classmethod
    def severity_is_known(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if value not in INCIDENT_SEVERITIES:
            raise ValueError(f"Severity must be one of {', '.join(INCIDENT_SEVERITIES)}.")
        return value

    @field_validator("status")
    @classmethod
    def status_is_known(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if value not in INCIDENT_STATUSES:
            raise ValueError(f"Status must be one of {', '.join(INCIDENT_STATUSES)}.")
        return value

    @field_validator("started_at")
    @classmethod
    def started_at_is_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
