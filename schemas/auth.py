"""Request schemas for authentication."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MIN_PASSWORD_LENGTH = 10


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)
    # Optional: the organization created alongside the first user. Defaults to the
    # user's name if omitted.
    organization_name: str | None = Field(default=None, max_length=160)

    @field_validator("password")
    @classmethod
    def password_is_not_only_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password must not be blank.")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
