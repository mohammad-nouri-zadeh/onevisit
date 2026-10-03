"""Test dello scenario demo su Postgres vero (storia D1)."""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from onevisit_analytics import generate_demo_data
from onevisit_db import repo

pytestmark = pytest.mark.db
TODAY = date(2026, 10, 3)


@pytest.fixture
def session(migrated_db_url: str) -> Iterator[Session]:
    engine: Engine = create_engine(migrated_db_url)
    with engine.connect() as conn:
        trans = conn.begin()
        s = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield s
        finally:
            s.close()
            trans.rollback()
    engine.dispose()


def test_same_seed_gives_same_counts_and_is_idempotent(session: Session) -> None:
    first = generate_demo_data(session, seed=42, weeks=8, today=TODAY)

    second = generate_demo_data(session, seed=42, weeks=8, today=TODAY)

    total = session.execute(text("SELECT count(*) FROM core.cases WHERE synthetic")).scalar()
    assert first == second
    assert total == first.cases == 400


def test_main_gap_passes_threshold_in_week_four_and_is_fixed_in_week_five(
    session: Session,
) -> None:
    summary = generate_demo_data(session, seed=42, weeks=8, today=TODAY)

    assert summary.threshold_week == 4
    assert summary.intervention_week == 5
    assert summary.main_gap_cases_by_week[0] == 0
    assert summary.main_gap_cases_by_week[1] > 0


def test_first_visit_rate_rises_after_the_intervention(session: Session) -> None:
    generate_demo_data(session, seed=42, weeks=8, today=TODAY)

    effects = repo.read_intervention_effect(session)

    assert len(effects) == 1
    effect = effects[0]
    assert effect.approved_at.date() > date(2026, 8, 1)
    assert effect.rate_before is not None and effect.rate_after is not None
    assert effect.rate_after > effect.rate_before


def test_demo_gaps_include_one_below_threshold_and_one_national(session: Session) -> None:
    generate_demo_data(session, seed=42, weeks=8, today=TODAY)

    gaps = repo.list_gaps(session)

    assert any(g.case_count < 5 for g in gaps)
    assert any(g.recipient == "ente-nazionale" and g.owner_ente for g in gaps)
    assert all(g.synthetic for g in gaps)


def test_demo_intervention_is_a_citizen_requirement_not_the_editor_draft(
    session: Session,
) -> None:
    generate_demo_data(session, seed=42, weeks=8, today=TODAY)

    [correction] = repo.approved_corrections(session)

    assert correction.requirement_id == "documenti-esteri"
    for value in (correction.text_it, correction.text_en or ""):
        assert value
        assert "Pagina da modificare" not in value and "Page to change" not in value
        assert "publish" not in value.lower() and "pubblicazione" not in value.lower()


def test_gap_summaries_carry_no_case_count(session: Session) -> None:
    generate_demo_data(session, seed=42, weeks=8, today=TODAY)

    for gap in repo.list_gaps(session):
        assert not any(ch.isdigit() for ch in (gap.summary or "").split(",")[0])
