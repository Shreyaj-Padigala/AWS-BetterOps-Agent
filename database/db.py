"""Database engine and session management.

Plain SQLAlchemy rather than Flask-SQLAlchemy: from Phase 9 the investigation workers run
outside any Flask application context and must share this exact data layer.

Two ways to obtain a session:

* `session_scope()` — a context manager that commits on success and rolls back on error.
  Used by workers, scripts and tests.
* `get_session()` — the session bound to the current Flask request, created on first use
  and closed by the teardown handler registered in `init_app`.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from config import Config, get_config

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None

# Key used to stash the request-scoped session on Flask's `g`.
_SESSION_KEY = "db_session"


def _build_engine(config: Config) -> Engine:
    url = config.database.url
    kwargs: dict = {"echo": config.database.echo, "future": True, "pool_pre_ping": True}

    if url.startswith("sqlite"):
        # SQLite is only used by the test suite. An in-memory database lives inside a
        # single connection, so every session must share one.
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool
        kwargs.pop("pool_pre_ping")
    else:
        kwargs["pool_size"] = config.database.pool_size
        kwargs["max_overflow"] = config.database.max_overflow

    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        # SQLAlchemy does not enable SQLite foreign keys by default, which would let the
        # tests pass constraints that PostgreSQL enforces in production.
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine(get_config())
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False, future=True
        )
    return _session_factory


def reset_engine() -> None:
    """Dispose the engine and forget the session factory.

    Tests call this after changing configuration so the next session uses the new URL.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for code that is not inside a Flask request."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Session:
    """The session bound to the current Flask request."""
    from flask import g

    session = getattr(g, _SESSION_KEY, None)
    if session is None:
        session = get_session_factory()()
        setattr(g, _SESSION_KEY, session)
    return session


def init_app(app) -> None:
    """Register the teardown handler that closes the request-scoped session."""

    @app.teardown_appcontext
    def _close_session(exception: BaseException | None) -> None:
        from flask import g

        session = g.pop(_SESSION_KEY, None)
        if session is None:
            return
        if exception is not None:
            session.rollback()
        session.close()
