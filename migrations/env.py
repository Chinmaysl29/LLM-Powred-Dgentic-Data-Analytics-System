from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import String, inspect, text
from alembic.ddl.postgresql import PostgresqlImpl

from alembic import context


class ProjectPostgresqlImpl(PostgresqlImpl):
    """Preserve published revision IDs, including those longer than 32 chars."""
    __dialect__ = "postgresql"

    def version_table_impl(self, **kwargs):
        table = super().version_table_impl(**kwargs)
        table.c.version_num.type = String(128)
        return table

# Ensure root workspace is in sys.path
sys.path.insert(0, os.path.abspath("."))

from backend.app.core.config import get_settings
from backend.app.models.base import Base
import backend.app.models  # noqa: F401 - ensure all models are registered

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set database URL from application configuration
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.postgres_dsn)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def _include_object(object_, name, type_, reflected, compare_to):
    """Keep Alembic's own version table out of model-diff generation."""
    return not (type_ == "table" and name == "alembic_version")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Widen existing bookkeeping without changing or stamping its revision.
        # This also supports databases left at revision 002 by the old 32-char limit.
        with connection.begin():
            inspector = inspect(connection)
            if connection.dialect.name == "postgresql" and inspector.has_table("alembic_version"):
                column = next(c for c in inspector.get_columns("alembic_version") if c["name"] == "version_num")
                if getattr(column["type"], "length", 128) < 128:
                    connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=_include_object,
            transaction_per_migration=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
