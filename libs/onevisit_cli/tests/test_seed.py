"""Test del comando seed-demo (storia D1)."""

from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onevisit_cli import seed


def test_seed_without_database_url_returns_config_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = seed.run(database_url="", seed=42, weeks=8)

    assert code == seed.EXIT_CONFIG
    assert "ONEVISIT_DATABASE_URL" in capsys.readouterr().out


@pytest.mark.db
def test_seed_creates_synthetic_cases_and_prints_counts(
    migrated_db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = seed.run(database_url=migrated_db_url, seed=42, weeks=8, today=date(2026, 10, 3))

    engine = create_engine(migrated_db_url)
    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM core.cases WHERE synthetic")).scalar()
    engine.dispose()
    assert code == 0
    assert total == 400
    assert "400 casi sintetici" in capsys.readouterr().out
