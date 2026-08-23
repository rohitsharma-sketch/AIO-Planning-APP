import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.base import Base, DATABASE_URL  # noqa: E402
from db import models  # noqa: E402,F401  (registers all model classes on Base.metadata)

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata

# Schemas are created by this env, not left to the DBA — Postgres won't let a
# table be created in a schema that doesn't exist yet.
SCHEMAS = ["masterdata", "calendar", "planning_inputs", "sync", "engine", "auth", "workflow", "audit"]


def include_name(name, type_, parent_names):
    # Autogenerate reflects every schema (include_schemas=True) including
    # "public", where Alembic's own version table lives — exclude it and any
    # other object not owned by our models so it never shows up in a diff.
    if type_ == "table" and name == "alembic_version":
        return False
    if type_ == "schema":
        return name in SCHEMAS
    return True


def run_migrations_offline():
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="public",
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        for schema in SCHEMAS:
            connection.execute(__import__("sqlalchemy").text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema="public",
            include_schemas=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
