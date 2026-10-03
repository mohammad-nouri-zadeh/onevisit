"""Schemi di base e permessi di utilizzo.

I ruoli di login (app_assistant, app_notifier, app_analysis, app_dashboard) sono
creati dallo script di inizializzazione di Postgres in docker/postgres/init/.
Qui si concedono solo i permessi sugli schemi. I permessi sulle tabelle vanno
concessi nella stessa migrazione che crea ciascuna tabella.

Revision ID: 0001
Revises:
Create Date: 2026-10-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    for schema in ("pii", "core", "analytics"):
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        op.execute(f"REVOKE ALL ON SCHEMA {schema} FROM PUBLIC")

    op.execute("GRANT USAGE ON SCHEMA pii TO app_assistant, app_notifier")
    op.execute("GRANT USAGE ON SCHEMA core TO app_assistant, app_analysis, app_dashboard")
    op.execute("GRANT USAGE ON SCHEMA analytics TO app_analysis, app_dashboard")


def downgrade() -> None:
    for schema in ("analytics", "core", "pii"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
