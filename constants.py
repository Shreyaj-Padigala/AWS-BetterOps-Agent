"""Domain vocabularies.

These are stored as VARCHAR rather than PostgreSQL ENUM types (see architecture.md §5):
the vocabularies grow as later phases land, and altering an ENUM takes a lock. Validation
happens in the schema/service layer.
"""

from __future__ import annotations

# --- Organization roles -----------------------------------------------------

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

ORGANIZATION_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER)

# Roles permitted to create or modify projects.
PROJECT_WRITE_ROLES = (ROLE_OWNER, ROLE_ADMIN)


# --- Incident severity ------------------------------------------------------

SEV1 = "SEV-1"
SEV2 = "SEV-2"
SEV3 = "SEV-3"
SEV4 = "SEV-4"

INCIDENT_SEVERITIES = (SEV1, SEV2, SEV3, SEV4)


# --- Incident status --------------------------------------------------------

INCIDENT_OPEN = "OPEN"
INCIDENT_INVESTIGATING = "INVESTIGATING"
INCIDENT_MITIGATED = "MITIGATED"
INCIDENT_RESOLVED = "RESOLVED"
INCIDENT_CLOSED = "CLOSED"

INCIDENT_STATUSES = (
    INCIDENT_OPEN,
    INCIDENT_INVESTIGATING,
    INCIDENT_MITIGATED,
    INCIDENT_RESOLVED,
    INCIDENT_CLOSED,
)

# Statuses that mean the incident no longer needs attention.
INCIDENT_TERMINAL_STATUSES = (INCIDENT_RESOLVED, INCIDENT_CLOSED)


# --- Incident source --------------------------------------------------------

SOURCE_MANUAL = "manual"
SOURCE_ALERT = "alert"
SOURCE_SIMULATOR = "simulator"

INCIDENT_SOURCES = (SOURCE_MANUAL, SOURCE_ALERT, SOURCE_SIMULATOR)


# --- Investigation status (Phase 9; listed here so the vocabulary lives in one place)

INVESTIGATION_QUEUED = "QUEUED"
INVESTIGATION_TRIAGING = "TRIAGING"
INVESTIGATION_COLLECTING_EVIDENCE = "COLLECTING_EVIDENCE"
INVESTIGATION_ANALYZING = "ANALYZING"
INVESTIGATION_COMPLETED = "COMPLETED"
INVESTIGATION_FAILED = "FAILED"
INVESTIGATION_CANCELLED = "CANCELLED"

INVESTIGATION_STATUSES = (
    INVESTIGATION_QUEUED,
    INVESTIGATION_TRIAGING,
    INVESTIGATION_COLLECTING_EVIDENCE,
    INVESTIGATION_ANALYZING,
    INVESTIGATION_COMPLETED,
    INVESTIGATION_FAILED,
    INVESTIGATION_CANCELLED,
)


# --- Root cause categories (Phase 15 deterministic evaluation) ---------------

ROOT_CAUSE_CATEGORIES = (
    "DATABASE_N_PLUS_ONE",
    "DATABASE_MISSING_INDEX",
    "DATABASE_CONNECTION_EXHAUSTION",
    "APPLICATION_EXCEPTION",
    "CONFIGURATION_ERROR",
    "EXTERNAL_API_TIMEOUT",
    "FAILED_DEPLOYMENT",
    "CPU_EXHAUSTION",
    "UNKNOWN",
)
