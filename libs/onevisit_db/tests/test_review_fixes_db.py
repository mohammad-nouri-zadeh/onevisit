"""Regressioni dalla revisione privacy e correttezza (storie B8, B9, C9, C11)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onevisit_db import repo
from onevisit_db.errors import InvalidFieldError

pytestmark = pytest.mark.db

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
PHONE_DIGEST = "b" * 64


def _case(s: Session) -> uuid.UUID:
    return repo.create_case(
        s,
        service_id="residenza-extra-ue",
        variant=None,
        category="extra-ue",
        language="en",
        office_id=None,
        appointment_week=date(2026, 9, 28),
        deadline_days=None,
        answers={},
        synthetic=True,
    )


def _phone_contact(s: Session, *, expires_at: datetime = NOW + timedelta(days=90)) -> uuid.UUID:
    return repo.create_contact(
        s,
        email_enc=None,
        email_hmac=None,
        phone_enc=b"\x00cifrato",
        phone_hmac=PHONE_DIGEST,
        preferred_channel="sms",
        fallback_channel=None,
        language="en",
        consents={"reminder": NOW.isoformat(), "followup": NOW.isoformat(), "correction": None},
        expires_at=expires_at,
    )


def _statuses(s: Session, case_id: uuid.UUID) -> dict[str, str]:
    rows = s.execute(
        text("SELECT kind, status FROM core.notifications WHERE case_id = :c"), {"c": case_id}
    ).all()
    return {str(k): str(v) for k, v in rows}


def test_stop_revokes_every_contact_with_same_phone(session: Session) -> None:
    cases = [_case(session), _case(session)]
    contacts = [_phone_contact(session), _phone_contact(session)]
    for case_id, contact_id in zip(cases, contacts, strict=True):
        repo.link_contact(session, case_id, contact_id)
        repo.schedule_notification(
            session, case_id=case_id, kind="reminder", channel="sms", due_at=NOW
        )

    revoked = repo.revoke_consents_by_phone_digest(session, PHONE_DIGEST)

    assert sorted(revoked) == sorted(contacts)
    for contact_id in contacts:
        contact = repo.get_contact(session, contact_id)
        assert contact is not None and all(v is None for v in contact.consents.values())
    assert repo.due_notifications(session, now=NOW + timedelta(days=1)) == []


def test_record_outcome_cancels_followup_and_nudge(session: Session) -> None:
    case_id = _case(session)
    for kind in ("reminder", "followup", "followup_nudge"):
        repo.schedule_notification(session, case_id=case_id, kind=kind, channel="sms", due_at=NOW)

    repo.record_outcome(
        session,
        case_id,
        outcome="ok",
        cause=None,
        missing_requirement_id=None,
        closed_in_time=True,
        rating=None,
    )

    assert _statuses(session, case_id) == {
        "reminder": "scheduled",
        "followup": "cancelled",
        "followup_nudge": "cancelled",
    }


def test_delete_and_purge_remove_notifications_derived_from_the_exact_day(
    session: Session,
) -> None:
    case_id = _case(session)
    contact_id = _phone_contact(session, expires_at=NOW - timedelta(days=1))
    repo.link_contact(session, case_id, contact_id)
    repo.create_appointment(
        session, contact_id=contact_id, case_id=case_id, starts_at=NOW, office_id="x"
    )
    repo.schedule_notification(
        session, case_id=case_id, kind="followup", channel="sms", due_at=NOW + timedelta(days=1)
    )

    repo.purge_expired(session, now=NOW)

    assert _statuses(session, case_id) == {}
    assert repo.appointment_for_case(session, case_id) is None


def test_k_threshold_floor_in_repo_and_database(session: Session) -> None:
    with pytest.raises(InvalidFieldError):
        repo.set_config(session, "k_threshold", 1)
    with pytest.raises(IntegrityError):
        session.execute(text("UPDATE analytics.config SET value = 1 WHERE key = 'k_threshold'"))
