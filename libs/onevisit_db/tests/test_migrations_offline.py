"""Le migrazioni generano SQL valido anche senza database (modalita' offline)."""

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _offline_sql(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("ONEVISIT_DATABASE_URL", "postgresql+psycopg://user@localhost/onevisit")
    buffer = io.StringIO()
    config = Config(str(ALEMBIC_INI), stdout=buffer)
    with redirect_stdout(buffer):
        command.upgrade(config, "head", sql=True)
    return buffer.getvalue()


def test_baseline_creates_the_three_schemas(monkeypatch: pytest.MonkeyPatch) -> None:
    sql = _offline_sql(monkeypatch)

    for schema in ("pii", "core", "analytics"):
        assert f"CREATE SCHEMA IF NOT EXISTS {schema}" in sql


def test_dashboard_role_never_gets_access_to_pii(monkeypatch: pytest.MonkeyPatch) -> None:
    sql = _offline_sql(monkeypatch)

    pii_grants = [line for line in sql.splitlines() if "ON SCHEMA pii" in line]
    assert pii_grants
    assert all("app_dashboard" not in line for line in pii_grants)


def test_core_pii_analytics_tables_and_views_are_created(monkeypatch: pytest.MonkeyPatch) -> None:
    sql = _offline_sql(monkeypatch)

    for table in ("core.cases", "core.notifications", "pii.contacts", "analytics.config"):
        assert f"CREATE TABLE {table}" in sql
    for view in ("first_visit_rate", "weekly_first_visit", "intervention_effect"):
        assert f"CREATE VIEW analytics.{view}" in sql
    assert "security_invoker" not in sql


def test_dashboard_never_granted_on_pii_or_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    sql = _offline_sql(monkeypatch)
    statements = [s for s in sql.split(";") if "GRANT" in s and "app_dashboard" in s]

    assert statements
    for statement in statements:
        assert "pii." not in statement
        assert "core.cases" not in statement
