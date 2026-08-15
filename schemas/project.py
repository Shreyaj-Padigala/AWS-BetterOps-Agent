"""Request schemas for projects."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{1,31}$")


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    key: str = Field(min_length=2, max_length=32)
    description: str | None = Field(default=None, max_length=4000)
    primary_service: str | None = Field(default=None, max_length=120)
    repository_url: str | None = Field(default=None, max_length=400)

    @field_validator("key")
    @classmethod
    def key_is_uppercase_identifier(cls, value: str) -> str:
        value = value.upper()
        if not KEY_PATTERN.match(value):
            raise ValueError(
                "Key must start with a letter and contain only A-Z, 0-9, '-' and '_'."
            )
        return value

    @field_validator("repository_url")
    @classmethod
    def repository_url_is_http(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("Repository URL must start with http:// or https://.")
        return value


class UpdateProjectRequest(BaseModel):
    """All fields optional — only supplied fields are applied."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    primary_service: str | None = Field(default=None, max_length=120)
    repository_url: str | None = Field(default=None, max_length=400)

    @field_validator("repository_url")
    @classmethod
    def repository_url_is_http(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("Repository URL must start with http:// or https://.")
        return value
