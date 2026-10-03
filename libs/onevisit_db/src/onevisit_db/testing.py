"""Database di test usa e getta con migrazioni applicate (storia C2).

Nome univoco per ogni chiamata, cosi' piu' agenti o processi pytest non si scontrano.
"""

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
APP_ROLES = ("app_assistant", "app_notifier", "app_analysis", "app_dashboard")
# Byte casuali nel nome del database (12 cifre esadecimali).
_NAME_BYTES = 6


def upgrade_to_head(database_url: str) -> None:
    """Applica tutte le migrazioni al database indicato."""
    config = Config(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")


@contextmanager
def migrated_database(admin_url: str) -> Iterator[str]:
    """Crea un database ``onevisit_t_<hex>``, applica le migrazioni, lo elimina alla fine."""
    base = make_url(admin_url)
    name = f"onevisit_t_{secrets.token_hex(_NAME_BYTES)}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
            conn.execute(text(f'REVOKE ALL ON DATABASE "{name}" FROM PUBLIC'))
            conn.execute(text(f'GRANT CONNECT ON DATABASE "{name}" TO {", ".join(APP_ROLES)}'))
        url = base.set(database=name).render_as_string(hide_password=False)
        try:
            upgrade_to_head(url)
            yield url
        finally:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        admin.dispose()
