import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Make `src` importable regardless of the cwd this is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infrastructure.config import Settings  # noqa: E402
from src.infrastructure.persistence.models import Base, UTCDateTime  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate compares the live DB against this metadata - the same
# `Base` the ORM models in models.py are registered on.
target_metadata = Base.metadata


def get_url() -> str:
    """Read DATABASE_URL through the app's own config module (env vars/.env)
    instead of duplicating it in alembic.ini, so switching from SQLite to
    Postgres is still just an environment variable change."""
    return Settings().database_url


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Render our custom UTCDateTime TypeDecorator as its underlying
    DateTime(timezone=True) in generated migration scripts.

    Without this, autogenerate emits a reference to
    `src.infrastructure.persistence.models.UTCDateTime` with no import for
    it, which is both a NameError waiting to happen and unwanted coupling of
    historical migration files to an application code path that may move.
    The actual DDL is identical either way - UTCDateTime.impl already is
    DateTime(timezone=True).
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, render_item=render_item
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = create_async_engine(get_url(), poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
