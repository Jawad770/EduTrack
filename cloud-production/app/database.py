"""Cloud database engine (accounts only — not school operational data).

Supports:
- SQLite for local development (default when DATABASE_URL is unset/sqlite)
- PostgreSQL 16+ for production via DATABASE_URL

Never silently falls back from PostgreSQL to SQLite.
"""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()
DATABASE_URL = (settings.database_url or "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is empty. Set a SQLite URL for local development or a "
        "postgresql+psycopg2://… URL for production."
    )

_is_sqlite = DATABASE_URL.startswith("sqlite")
_is_postgres = DATABASE_URL.startswith("postgresql")

if not _is_sqlite and not _is_postgres:
    raise RuntimeError(
        f"Unsupported DATABASE_URL scheme. Use sqlite:// or postgresql+psycopg2:// "
        f"(got: {DATABASE_URL.split(':', 1)[0]!r})."
    )

_engine_kwargs: dict = {"pool_pre_ping": True}
if _is_sqlite:
    _engine_kwargs.update(
        {
            "connect_args": {"check_same_thread": False, "timeout": 30},
            "poolclass": StaticPool,
        }
    )
else:
    # Production PostgreSQL: small pool suitable for a single uvicorn worker on VPS
    _engine_kwargs.update(
        {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_recycle": 1800,
        }
    )

engine = create_engine(DATABASE_URL, **_engine_kwargs)


@event.listens_for(Engine, "connect")
def _sqlite_on_connect(dbapi_connection, _record) -> None:
    # Only SQLite PRAGMAs — never rewrite connection target.
    if not _is_sqlite:
        return
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_database_connection() -> None:
    """
    Open a real connection and fail loudly on error.

    PostgreSQL production must not continue (or fall back to SQLite) if PG is down.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        kind = "PostgreSQL" if _is_postgres else "SQLite"
        raise RuntimeError(
            f"EduTrack Cloud cannot connect to {kind} database. "
            f"Check DATABASE_URL and that the server is reachable. Detail: {exc}"
        ) from exc


def init_db(*, run_migrations: bool = True) -> None:
    """Verify connectivity, then apply schema (Alembic preferred, create_all fallback)."""
    from app import models  # noqa: F401

    verify_database_connection()

    if run_migrations:
        try:
            _run_alembic_upgrade()
            logger.info("cloud database migrations applied (%s)", "sqlite" if _is_sqlite else "postgresql")
            return
        except Exception as exc:  # noqa: BLE001
            # Fresh install without alembic CLI path — fall through to create_all
            logger.warning("alembic upgrade skipped/failed (%s); using create_all", exc)

    Base.metadata.create_all(bind=engine)
    logger.info("cloud database schema ensured via create_all")


def _run_alembic_upgrade() -> None:
    """Run alembic upgrade head against the configured DATABASE_URL."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent
    ini = root / "alembic.ini"
    if not ini.is_file():
        raise FileNotFoundError(f"alembic.ini not found at {ini}")

    cfg = Config(str(ini))
    # Escape % for ConfigParser (URL-encoded passwords)
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(cfg, "head")


def get_engine_dialect_name() -> str:
    return engine.dialect.name
