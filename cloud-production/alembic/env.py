"""Alembic environment for EduTrack Cloud (SQLite + PostgreSQL)."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.database import Base
from app import models  # noqa: F401

config = context.config
settings = get_settings()

db_url = os.environ.get("DATABASE_URL") or settings.database_url
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=url.startswith("sqlite") if url else False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or db_url
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=is_sqlite,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
