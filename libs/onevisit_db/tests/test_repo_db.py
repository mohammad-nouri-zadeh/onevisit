"""Round trip delle funzioni di onevisit_db.repo sul database reale (storie C2, C9)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from onevisit_db import repo
from onevisit_db.errors import InvalidFieldError

pytestmark = pytest.mark.db

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
WEEK = date(2026, 9, 28)


def _case(s: Session, **overrides: object) -> uuid.UUID:
    fields: dict[str, object] = {
        "service_id": "residenza-extra-ue",
        "variant": None,
        "category": "extra-ue",
        "language": "en",
        "office_id": "anagrafe-larga",
        "appointment_week": WEEK,
        "deadline_days": 10,
        "answers": {"arrivo": "estero"},
        "synthetic": True,
    }
    fields.update(overrides)
    return repo.create_case(s, **fields)  # type: ignore[arg-type]


def _contact(s: Session, *, expires_at: datetime = NOW + timedelta(days=90)) -> uuid.UUID:
    return repo.create_contact(
        s,
        email_enc=b"\x00cifrato",
        email_hmac="a" * 64,
        phone_enc=None,
        phone_hmac=None,
        preferred_channel="email",
        fallback_channel=None,
        language="en",
        consents={"reminder": NOW.isoformat(), "followup": NOW.isoformat(), "correction": None},
        expires_at=expires_at,
    )


def _gap(s: Session) -> uuid.UUID:
    gap_id = uuid.uuid4()
    s.execute(
        text(
            "INSERT INTO core.gaps (id, service_id, cause, title, recipient, requirement_id, "
            "case_count) VALUES (:id, 'residenza-extra-ue', 'pagina-incompleta', "
            "'Traduzione mancante', 'redazione', 'req-traduzione', 7)"
        ),
        {"id": gap_id},
    )
    return gap_id


def test_case_and_answers_round_trip(session: Session) -> None:
    case_id = _case(session)
    repo.update_case(session, case_id, office_id="anagrafe-sud")
    repo.record_outcome(
        session,
        case_id,
        outcome="missing",
        cause="pagina-incompleta",
        missing_requirement_id="req-traduzione",
        closed_in_time=False,
        rating=2,
    )

    case = repo.get_case(session, case_id)
    assert case is not None
    assert case.office_id == "anagrafe-sud"
    assert case.outcome == "missing"
    assert case.outcome_at is not None
    assert repo.case_answers(session, case_id) == {"arrivo": "estero"}
    with pytest.raises(InvalidFieldError):
        repo.update_case(session, case_id, contact_ref=uuid.uuid4())


def test_contact_appointment_and_link(session: Session) -> None:
    case_id = _case(session)
    contact_id = _contact(session)
    repo.confirm_contact(session, contact_id)
    repo.link_contact(session, case_id, contact_id)
    repo.create_appointment(
        session, contact_id=contact_id, case_id=case_id, starts_at=NOW, office_id="anagrafe-larga"
    )

    contact = repo.get_contact(session, contact_id)
    assert contact is not None and contact.confirmed_at is not None
    case = repo.get_case(session, case_id)
    assert case is not None and case.contact_ref == contact_id
    appointment = repo.appointment_for_case(session, case_id)
    assert appointment is not None and appointment.office_id == "anagrafe-larga"


def test_revoke_cancels_scheduled_notifications(session: Session) -> None:
    case_id = _case(session)
    contact_id = _contact(session)
    repo.link_contact(session, case_id, contact_id)
    repo.schedule_notification(
        session, case_id=case_id, kind="reminder", channel="email", due_at=NOW
    )

    repo.revoke_consents(session, contact_id)

    contact = repo.get_contact(session, contact_id)
    assert contact is not None
    assert all(v is None for v in contact.consents.values())
    assert repo.due_notifications(session, now=NOW + timedelta(days=1)) == []


def test_delete_contact_removes_contact_ref(session: Session) -> None:
    case_id = _case(session)
    contact_id = _contact(session)
    repo.link_contact(session, case_id, contact_id)
    repo.create_appointment(
        session, contact_id=contact_id, case_id=case_id, starts_at=NOW, office_id="x"
    )

    repo.delete_contact(session, contact_id)

    assert repo.get_contact(session, contact_id) is None
    assert repo.appointment_for_case(session, case_id) is None
    case = repo.get_case(session, case_id)
    assert case is not None and case.contact_ref is None


def test_due_notifications_order_and_mark(session: Session) -> None:
    case_id = _case(session)
    late = repo.schedule_notification(
        session, case_id=case_id, kind="followup", channel="sms", due_at=NOW - timedelta(hours=1)
    )
    early = repo.schedule_notification(
        session, case_id=case_id, kind="reminder", channel="email", due_at=NOW - timedelta(days=1)
    )
    repo.schedule_notification(
        session,
        case_id=case_id,
        kind="followup_nudge",
        channel="sms",
        due_at=NOW + timedelta(days=1),
    )

    due = repo.due_notifications(session, now=NOW)
    assert [n.id for n in due] == [early, late]

    repo.mark_notification(session, early, status="sent")
    due = repo.due_notifications(session, now=NOW)
    assert [n.id for n in due] == [late]
    sent = session.execute(
        text("SELECT attempts, sent_at FROM core.notifications WHERE id = :id"), {"id": early}
    ).one()
    assert sent.attempts == 1 and sent.sent_at is not None


def test_approve_gap_creates_intervention(session: Session) -> None:
    gap_id = _gap(session)

    intervention_id = repo.approve_gap(
        session,
        gap_id,
        approved_by="redazione",
        text_it="Serve la traduzione.",
        text_easy_it=None,
        text_en="A translation is needed.",
    )

    gap = repo.get_gap(session, gap_id)
    assert gap is not None and gap.status == "corretta"
    corrections = repo.approved_corrections(session)
    assert [c.id for c in corrections] == [intervention_id]
    assert corrections[0].requirement_id == "req-traduzione"
    assert [g.id for g in repo.list_gaps(session, status="corretta")] == [gap_id]

    other = _gap(session)
    repo.archive_gap(session, other, reason="duplicata")
    archived = repo.get_gap(session, other)
    assert archived is not None and archived.status == "archiviata"
    repo.log_access(session, role="direzione", action="approve", object_id=str(gap_id))


def test_purge_expired(session: Session) -> None:
    case_id = _case(session)
    expired = _contact(session, expires_at=NOW - timedelta(days=1))
    alive = _contact(session)
    repo.link_contact(session, case_id, expired)
    repo.record_outcome(
        session,
        case_id,
        outcome="ok",
        cause=None,
        missing_requirement_id=None,
        closed_in_time=True,
        rating=5,
    )

    result = repo.purge_expired(session, now=NOW)

    assert result.contacts_deleted == 1 and result.cases_unlinked == 1
    assert repo.get_contact(session, expired) is None
    assert repo.get_contact(session, alive) is not None
    case = repo.get_case(session, case_id)
    assert case is not None and case.contact_ref is None
    assert case.outcome_at is not None and case.outcome_at.day == 1


def _outcomes(session: Session, n: int, *, service_id: str, week: date, ok: int) -> None:
    for i in range(n):
        case_id = _case(session, service_id=service_id, appointment_week=week)
        repo.record_outcome(
            session,
            case_id,
            outcome="ok" if i < ok else "missing",
            cause=None,
            missing_requirement_id=None,
            closed_in_time=None,
            rating=None,
        )


def test_k_filter_hides_small_groups(session: Session) -> None:
    _outcomes(session, 4, service_id="servizio-piccolo", week=WEEK, ok=2)
    _outcomes(session, 5, service_id="servizio-grande", week=WEEK, ok=4)

    rates = {r.service_id: r for r in repo.read_first_visit_rate(session)}
    assert "servizio-piccolo" not in rates
    assert rates["servizio-grande"].cases == 5
    assert rates["servizio-grande"].rate == pytest.approx(0.8)
    weekly = {r.service_id for r in repo.read_weekly_first_visit(session)}
    assert weekly == {"servizio-grande"}

    _outcomes(session, 1, service_id="servizio-piccolo", week=WEEK, ok=1)
    rates = {r.service_id: r for r in repo.read_first_visit_rate(session)}
    assert rates["servizio-piccolo"].cases == 5


def test_intervention_effect_before_after(session: Session) -> None:
    approved = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    _outcomes(session, 5, service_id="servizio-x", week=date(2026, 8, 17), ok=2)
    _outcomes(session, 6, service_id="servizio-x", week=date(2026, 9, 14), ok=6)
    session.execute(
        text(
            "INSERT INTO core.interventions (id, service_id, text_it, approved_by, approved_at) "
            "VALUES (gen_random_uuid(), 'servizio-x', 'Correzione', 'redazione', :at)"
        ),
        {"at": approved},
    )
    repo.set_config(session, "cost_per_slot_eur", 20)

    effect = [e for e in repo.read_intervention_effect(session) if e.service_id == "servizio-x"]
    assert len(effect) == 1
    assert effect[0].cases_before == 5 and effect[0].rate_before == pytest.approx(0.4)
    assert effect[0].cases_after == 6 and effect[0].rate_after == pytest.approx(1.0)
    avoided = {a.service_id: a for a in repo.read_avoided_visits(session)}
    assert avoided["servizio-x"].avoided_visits == pytest.approx(4)
    assert avoided["servizio-x"].avoided_cost_eur == pytest.approx(72)

    repo.set_config(session, "k_threshold", 6)
    effect = [e for e in repo.read_intervention_effect(session) if e.service_id == "servizio-x"]
    assert effect[0].cases_before is None and effect[0].rate_before is None
    assert repo.read_config(session)["k_threshold"] == 6
    with pytest.raises(InvalidFieldError):
        repo.set_config(session, "inesistente", 1)


def test_gaps_by_cause_nulls_below_k(session: Session) -> None:
    _gap(session)

    rows = {r.cause: r for r in repo.read_gaps_by_cause(session)}
    assert rows["pagina-incompleta"].cases == 7
    repo.set_config(session, "k_threshold", 100)
    rows = {r.cause: r for r in repo.read_gaps_by_cause(session)}
    assert rows["pagina-incompleta"].cases is None
