"""Ambiente Alembic: online sul database, offline per generare SQL."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("ONEVISIT_DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Quando esisteranno i modelli, impostare qui il loro MetaData per l'autogenerazione.
target_metadata = None


def run_migrations_offline() -> None:
    """Genera lo SQL delle migrazioni senza connettersi al database."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Applica le migrazioni al database configurato."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
