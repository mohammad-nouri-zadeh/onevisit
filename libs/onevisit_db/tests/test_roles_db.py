"""Verifica dei permessi sul database reale (storia C2)."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError

pytestmark = pytest.mark.db


def test_database_is_reachable(database_url_test: str) -> None:
    engine = create_engine(database_url_test)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def _as_role(engine: Engine, role: str, sql: str) -> None:
    """Esegue ``sql`` con SET LOCAL ROLE in una transazione annullata."""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text(f"SET LOCAL ROLE {role}"))
            conn.execute(text(sql))
        finally:
            trans.rollback()


@pytest.mark.parametrize("table", ["pii.contacts", "pii.appointments", "core.cases"])
def test_dashboard_cannot_read_personal_tables(db_engine: Engine, table: str) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        _as_role(db_engine, "app_dashboard", f"SELECT * FROM {table}")  # noqa: S608 (nomi fissi dei test)


@pytest.mark.parametrize(
    "view",
    [
        "analytics.first_visit_rate",
        "analytics.weekly_first_visit",
        "analytics.gaps_by_cause",
        "analytics.intervention_effect",
        "analytics.avoided_visits",
        "analytics.config",
        "core.gaps",
        "core.interventions",
    ],
)
def test_dashboard_reads_analytics_and_gaps(db_engine: Engine, view: str) -> None:
    _as_role(db_engine, "app_dashboard", f"SELECT * FROM {view}")  # noqa: S608 (nomi fissi dei test)


def test_dashboard_may_update_config_and_log_access(db_engine: Engine) -> None:
    _as_role(
        db_engine,
        "app_dashboard",
        "UPDATE analytics.config SET value = 6 WHERE key = 'k_threshold'",
    )
    _as_role(
        db_engine,
        "app_dashboard",
        "INSERT INTO core.access_log (id, role, action) "
        "VALUES (gen_random_uuid(), 'direzione', 'view')",
    )


@pytest.mark.parametrize("table", ["pii.contacts", "pii.appointments"])
def test_analysis_cannot_read_pii(db_engine: Engine, table: str) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        _as_role(db_engine, "app_analysis", f"SELECT * FROM {table}")  # noqa: S608 (nomi fissi dei test)


def test_analysis_reads_cases_and_config(db_engine: Engine) -> None:
    _as_role(db_engine, "app_analysis", "SELECT * FROM core.cases")
    _as_role(db_engine, "app_analysis", "SELECT * FROM analytics.config")


def test_notifier_reads_contacts_and_cases(db_engine: Engine) -> None:
    _as_role(db_engine, "app_notifier", "SELECT * FROM pii.contacts")
    _as_role(db_engine, "app_notifier", "SELECT * FROM core.cases")
    _as_role(db_engine, "app_notifier", "UPDATE core.notifications SET attempts = attempts")


def test_notifier_cannot_write_contacts(db_engine: Engine) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        _as_role(db_engine, "app_notifier", "DELETE FROM pii.contacts")


def test_assistant_reads_interventions_and_config(db_engine: Engine) -> None:
    _as_role(db_engine, "app_assistant", "SELECT * FROM core.interventions")
    _as_role(db_engine, "app_assistant", "SELECT * FROM analytics.config")
    _as_role(db_engine, "app_assistant", "SELECT * FROM pii.contacts")


def test_assistant_cannot_read_gaps(db_engine: Engine) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        _as_role(db_engine, "app_assistant", "SELECT * FROM core.gaps")
