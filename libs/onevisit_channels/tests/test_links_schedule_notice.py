"""Link firmati, calcolo degli orari, informativa (B9, C8, A4)."""

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from itsdangerous import URLSafeTimedSerializer

from onevisit_channels import (
    PURPOSE_CHECKLIST,
    PURPOSE_REPLY,
    LinkError,
    LinkSigner,
    informativa,
    plan_notifications,
)

ROME = ZoneInfo("Europe/Rome")


def test_link_round_trip() -> None:
    signer = LinkSigner("test-secret")
    case_id, contact_id = uuid4(), uuid4()

    token = signer.sign(PURPOSE_REPLY, case_id, contact_id)

    assert signer.verify(token, PURPOSE_REPLY, max_age_s=60) == {
        "case_id": str(case_id),
        "contact_id": str(contact_id),
    }


def test_link_for_another_purpose_is_rejected() -> None:
    signer = LinkSigner("test-secret")
    token = signer.sign(PURPOSE_CHECKLIST, uuid4())

    with pytest.raises(LinkError):
        signer.verify(token, PURPOSE_REPLY, max_age_s=60)


def test_expired_link_is_rejected() -> None:
    signer = LinkSigner("test-secret")
    old = URLSafeTimedSerializer("test-secret", salt="onevisit.link." + PURPOSE_REPLY)
    token = str(old.dumps({"case_id": str(uuid4()), "contact_id": None}))

    with pytest.raises(LinkError):
        signer.verify(token, PURPOSE_REPLY, max_age_s=-1)


def test_plan_normal_appointment() -> None:
    now = datetime(2026, 10, 3, 12, 0, tzinfo=ROME)
    appointment = datetime(2026, 10, 15, 9, 30, tzinfo=ROME)

    plan = dict(plan_notifications(appointment_at=appointment, now=now))

    assert plan["reminder"] == datetime(2026, 10, 12, 10, 0, tzinfo=ROME)
    assert plan["followup"] == datetime(2026, 10, 16, 18, 0, tzinfo=ROME)
    assert plan["followup_nudge"] == datetime(2026, 10, 19, 18, 0, tzinfo=ROME)


def test_plan_close_appointment_sends_reminder_now() -> None:
    now = datetime(2026, 10, 3, 12, 0, tzinfo=ROME)
    appointment = datetime(2026, 10, 5, 9, 0, tzinfo=ROME)

    plan = dict(plan_notifications(appointment_at=appointment, now=now))

    assert plan["reminder"] == now


def test_plan_across_dst_keeps_local_hour() -> None:
    # L'ora legale finisce il 25 ottobre 2026: il promemoria resta alle 10:00 di Roma.
    now = datetime(2026, 10, 3, 12, 0, tzinfo=ROME)
    appointment = datetime(2026, 10, 27, 9, 0, tzinfo=ROME)

    plan = dict(plan_notifications(appointment_at=appointment, now=now))

    reminder = plan["reminder"].astimezone(ROME)
    assert (reminder.day, reminder.hour) == (24, 10)
    assert plan["reminder"].utcoffset() == timedelta(hours=2)
    assert plan["followup"].utcoffset() == timedelta(hours=1)
    assert plan["followup"].astimezone(ROME).hour == 18


def test_plan_demo_compresses_days() -> None:
    now = datetime(2026, 10, 3, 12, 0, tzinfo=ROME)
    appointment = now + timedelta(days=10)

    plan = dict(plan_notifications(appointment_at=appointment, now=now, seconds_per_day=60))

    assert now < plan["reminder"] < plan["followup"] < plan["followup_nudge"]
    assert plan["followup_nudge"] - now < timedelta(minutes=20)


def test_plan_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError):
        plan_notifications(appointment_at=datetime(2026, 10, 5), now=datetime(2026, 10, 3))


@pytest.mark.parametrize(
    ("language", "ai_words"),
    [("it", "intelligenza artificiale"), ("en", "artificial intelligence")],
)
def test_informativa_says_it_is_an_ai(language: str, ai_words: str) -> None:
    text = informativa(language)

    assert ai_words in text
    assert "Anthropic" in text
    assert "STOP" in text
    assert "DPO" in text
