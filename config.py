"""Centralised configuration.

Every environment-dependent value in the application is read here and nowhere else.
Modules import `get_config()` rather than calling `os.environ` directly, so that:

* model ids, TTLs and limits are never hard-coded across the codebase,
* tests can build an isolated `Config` without mutating the process environment,
* the full configuration surface is discoverable in one file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

DEVELOPMENT = "development"
TESTING = "testing"
PRODUCTION = "production"

# Cache backends. Redis is the real one; the others exist so the application still runs
# (and the suite still tests cache behaviour) without Redis available.
CACHE_BACKEND_REDIS = "redis"
CACHE_BACKEND_MEMORY = "memory"
CACHE_BACKEND_DISABLED = "disabled"
CACHE_BACKENDS = (CACHE_BACKEND_REDIS, CACHE_BACKEND_MEMORY, CACHE_BACKEND_DISABLED)

LOG_FORMAT_TEXT = "text"
LOG_FORMAT_JSON = "json"
LOG_FORMATS = (LOG_FORMAT_TEXT, LOG_FORMAT_JSON)

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _get_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _get_int(name: str, default: int) -> int:
    raw = _get_str(name)
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


def _get_float(name: str, default: float) -> float:
    raw = _get_str(name)
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from exc


def _get_bool(name: str, default: bool) -> bool:
    raw = _get_str(name)
    if raw == "":
        return default
    return raw.lower() in _TRUE_VALUES


@dataclass(frozen=True)
class DatabaseConfig:
    url: str
    pool_size: int
    max_overflow: int
    echo: bool


@dataclass(frozen=True)
class SecurityConfig:
    secret_key: str
    session_cookie_name: str
    session_ttl_seconds: int
    cookie_secure: bool
    cookie_samesite: str = "Strict"


@dataclass(frozen=True)
class CacheConfig:
    """Cache and rate limiting. TTLs are never invented at the call site."""

    # redis | memory | disabled. `memory` is for tests and for local development
    # without Redis; `disabled` turns every read into a miss.
    backend: str
    redis_url: str
    # Redis must never be able to stall a request: a slow cache is treated as a miss.
    socket_timeout_seconds: float
    ttl_github_commits: int
    ttl_github_file: int
    ttl_cloudwatch: int
    ttl_integration: int
    ttl_rag: int
    ttl_incident: int
    rate_limit_enabled: bool
    rate_limit_investigations_per_minute: int
    rate_limit_api_per_minute: int
    rate_limit_auth_per_minute: int


@dataclass(frozen=True)
class ModelConfig:
    """Phase 3. The only place a Bedrock model id may appear."""

    bedrock_region: str
    model_id: str
    embedding_model_id: str
    temperature: float
    max_output_tokens: int
    max_agent_steps: int
    max_tool_calls_per_agent: int
    max_agents_per_investigation: int
    max_model_calls_per_investigation: int
    max_investigation_seconds: int
    agent_timeout_seconds: int


@dataclass(frozen=True)
class AwsConfig:
    """Phases 5-9."""

    region: str
    endpoint_url: str
    s3_bucket_name: str
    sqs_queue_url: str
    sqs_visibility_timeout: int
    assume_role_external_id: str


@dataclass(frozen=True)
class Config:
    env: str
    host: str
    port: int
    log_level: str
    log_format: str
    database: DatabaseConfig
    security: SecurityConfig
    cache: CacheConfig
    model: ModelConfig
    aws: AwsConfig
    # Populated only when a phase needs them.
    extras: dict = field(default_factory=dict)

    @property
    def is_development(self) -> bool:
        return self.env == DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        return self.env == TESTING

    @property
    def is_production(self) -> bool:
        return self.env == PRODUCTION


def load_config() -> Config:
    """Build a `Config` from the current environment."""
    env = _get_str("APP_ENV", DEVELOPMENT).lower()
    if env not in {DEVELOPMENT, TESTING, PRODUCTION}:
        raise ValueError(
            f"APP_ENV must be one of {DEVELOPMENT}, {TESTING}, {PRODUCTION}; got {env!r}"
        )

    secret_key = _get_str("SECRET_KEY")
    if not secret_key:
        if env == PRODUCTION:
            raise ValueError("SECRET_KEY must be set in production")
        # Development and tests get a fixed, obviously-not-secret fallback so a fresh
        # checkout runs without setup. Production is guarded above.
        secret_key = "dev-only-insecure-secret-key"

    database_url = _get_str(
        "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/betterops"
    )
    if env == TESTING:
        database_url = _get_str("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")

    # Tests exercise real cache semantics without needing a Redis server.
    default_cache_backend = CACHE_BACKEND_MEMORY if env == TESTING else CACHE_BACKEND_REDIS
    cache_backend = _get_str("CACHE_BACKEND", default_cache_backend).lower()
    if cache_backend not in CACHE_BACKENDS:
        raise ValueError(f"CACHE_BACKEND must be one of {', '.join(CACHE_BACKENDS)}")

    # Human-readable logs locally; machine-parseable everywhere CloudWatch reads them.
    default_log_format = LOG_FORMAT_TEXT if env == DEVELOPMENT else LOG_FORMAT_JSON
    log_format = _get_str("LOG_FORMAT", default_log_format).lower()
    if log_format not in LOG_FORMATS:
        raise ValueError(f"LOG_FORMAT must be one of {', '.join(LOG_FORMATS)}")

    return Config(
        env=env,
        host=_get_str("FLASK_HOST", "127.0.0.1"),
        port=_get_int("FLASK_PORT", 5000),
        log_level=_get_str("LOG_LEVEL", "INFO").upper(),
        log_format=log_format,
        database=DatabaseConfig(
            url=database_url,
            pool_size=_get_int("DB_POOL_SIZE", 5),
            max_overflow=_get_int("DB_MAX_OVERFLOW", 10),
            echo=_get_bool("DB_ECHO", False),
        ),
        security=SecurityConfig(
            secret_key=secret_key,
            session_cookie_name=_get_str("SESSION_COOKIE_NAME", "betterops_session"),
            session_ttl_seconds=_get_int("SESSION_TTL_SECONDS", 12 * 60 * 60),
            # Secure cookies require HTTPS, which local development does not use.
            cookie_secure=env != DEVELOPMENT,
        ),
        cache=CacheConfig(
            backend=cache_backend,
            redis_url=_get_str("REDIS_URL", "redis://localhost:6379/0"),
            socket_timeout_seconds=_get_float("REDIS_SOCKET_TIMEOUT", 0.5),
            ttl_github_commits=_get_int("CACHE_TTL_GITHUB_COMMITS", 60),
            ttl_github_file=_get_int("CACHE_TTL_GITHUB_FILE", 300),
            ttl_cloudwatch=_get_int("CACHE_TTL_CLOUDWATCH", 10),
            ttl_integration=_get_int("CACHE_TTL_INTEGRATION", 300),
            ttl_rag=_get_int("CACHE_TTL_RAG", 900),
            ttl_incident=_get_int("CACHE_TTL_INCIDENT", 300),
            rate_limit_enabled=_get_bool("RATE_LIMIT_ENABLED", True),
            rate_limit_investigations_per_minute=_get_int(
                "RATE_LIMIT_INVESTIGATIONS_PER_MINUTE", 10
            ),
            rate_limit_api_per_minute=_get_int("RATE_LIMIT_API_PER_MINUTE", 120),
            rate_limit_auth_per_minute=_get_int("RATE_LIMIT_AUTH_PER_MINUTE", 20),
        ),
        model=ModelConfig(
            bedrock_region=_get_str("BEDROCK_REGION", _get_str("AWS_REGION", "us-east-1")),
            model_id=_get_str("BEDROCK_MODEL_ID", "amazon.nova-2-lite-v1:0"),
            embedding_model_id=_get_str(
                "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"
            ),
            temperature=_get_float("MODEL_TEMPERATURE", 0.2),
            max_output_tokens=_get_int("MODEL_MAX_OUTPUT_TOKENS", 2048),
            max_agent_steps=_get_int("MAX_AGENT_STEPS", 8),
            max_tool_calls_per_agent=_get_int("MAX_TOOL_CALLS_PER_AGENT", 12),
            max_agents_per_investigation=_get_int("MAX_AGENTS_PER_INVESTIGATION", 7),
            max_model_calls_per_investigation=_get_int("MAX_MODEL_CALLS_PER_INVESTIGATION", 40),
            max_investigation_seconds=_get_int("MAX_INVESTIGATION_SECONDS", 600),
            agent_timeout_seconds=_get_int("AGENT_TIMEOUT_SECONDS", 120),
        ),
        aws=AwsConfig(
            region=_get_str("AWS_REGION", "us-east-1"),
            endpoint_url=_get_str("AWS_ENDPOINT_URL"),
            s3_bucket_name=_get_str("S3_BUCKET_NAME", "betterops-documents"),
            sqs_queue_url=_get_str("SQS_QUEUE_URL"),
            sqs_visibility_timeout=_get_int("SQS_VISIBILITY_TIMEOUT", 900),
            assume_role_external_id=_get_str("AWS_ASSUME_ROLE_EXTERNAL_ID"),
        ),
    )


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Process-wide configuration. Cached so env parsing happens once."""
    return load_config()


def reset_config_cache() -> None:
    """Drop the cached config. Used by tests that change the environment."""
    get_config.cache_clear()
