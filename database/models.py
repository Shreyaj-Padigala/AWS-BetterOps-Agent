"""SQLAlchemy models for the AWS BetterOps Agent database.

This is the platform's own database. It must never be confused with a customer's
application database, which is reached read-only through the PostgreSQL MCP (Phase 6).

Phase 1 defines identity, tenancy, projects and incidents. Later phases add
investigations, agent runs, tool calls, evidence, documents and evaluation tables in
their own migrations.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from constants import INCIDENT_OPEN, ROLE_MEMBER, SEV3, SOURCE_MANUAL


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stored lowercased so uniqueness is case-insensitive without a functional index.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


class Organization(TimestampMixin, Base):
    """The tenant boundary. Every other business record hangs off an organization."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)

    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id} slug={self.slug!r}>"


class OrganizationMember(TimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
        Index("ix_org_member_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), default=ROLE_MEMBER, nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Project(TimestampMixin, Base):
    """A deployed system under observation: its repository, services and incidents."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_project_org_key"),
        Index("ix_project_org", "organization_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # Short human identifier, e.g. "CHECKOUT". Unique within the organization.
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The service most incidents in this project relate to, used to seed triage.
    primary_service: Mapped[str | None] = mapped_column(String(120), nullable=True)
    repository_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    organization: Mapped[Organization] = relationship()

    def __repr__(self) -> str:
        return f"<Project id={self.id} key={self.key!r}>"


class Incident(TimestampMixin, Base):
    """A production problem worth investigating."""

    __tablename__ = "incidents"
    __table_args__ = (
        # Incident lists are always "newest first, for one project".
        Index("ix_incident_project_started", "project_id", "started_at"),
        # The dashboard filters open incidents across a whole organization.
        Index("ix_incident_org_status", "organization_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(10), default=SEV3, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=INCIDENT_OPEN, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default=SOURCE_MANUAL, nullable=False)
    affected_service: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # When the problem began in production. This is the timestamp agents correlate
    # deployments and metric changes against, and it is distinct from created_at, which
    # is merely when somebody wrote the record down.
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Incidents are essentially always rendered with their project's name, so the join
    # is eager rather than an N+1 on every list view.
    project: Mapped[Project] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<Incident id={self.id} status={self.status!r}>"
