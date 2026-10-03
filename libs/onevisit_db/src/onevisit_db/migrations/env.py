"""Ambiente Alembic: online sul database, offline per generare SQL."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from onevisit_db.models import metadata

config = context.config
# Chi invoca Alembic da codice (onevisit_db.testing) puo' disattivare la configurazione
# dei log, che altrimenti sostituirebbe quella dell'applicazione o di pytest.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# La URL passata da codice ha la precedenza sulla variabile d'ambiente.
database_url = os.environ.get("ONEVISIT_DATABASE_URL")
if database_url and not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = metadata


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
