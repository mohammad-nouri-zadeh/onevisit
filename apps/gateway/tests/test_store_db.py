"""SqlNotifierStore su PostgreSQL vero: invio, poi STOP che annulla il resto (C8, B9)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from gateway.dispatcher import DispatchContext, RetryPolicy, Senders, dispatch_due
from gateway.personal_links import LinkBuilder
from gateway.store import SqlNotifierStore
from onevisit_channels import FakeEmailSender, FakeSmsProvider, render_notification

from .conftest import PHONE, FakeCipher

pytestmark = pytest.mark.db


async def test_dispatch_and_revoke_on_real_database(
    migrated_db_url: str, links: LinkBuilder, no_wait_retry: RetryPolicy
) -> None:
    from onevisit_db import repo

    cipher = FakeCipher()
    now = datetime.now(UTC)
    with Session(create_engine(migrated_db_url)) as s:
        case_id = repo.create_case(
            s,
            service_id="carta-identita",
            variant=None,
            category="extra-ue",
            language="it",
            office_id=None,
            appointment_week=date.today(),
            deadline_days=None,
            answers={},
            synthetic=True,
        )
        contact_id = repo.create_contact(
            s,
            email_enc=None,
            email_hmac=None,
            phone_enc=cipher.encrypt(PHONE),
            phone_hmac=cipher.digest(PHONE),
            preferred_channel="sms",
            fallback_channel=None,
            language="it",
            consents={"reminder": now.isoformat(), "followup": now.isoformat(), "correction": None},
            expires_at=now + timedelta(days=30),
        )
        repo.link_contact(s, case_id, contact_id)
        repo.create_appointment(
            s,
            contact_id=contact_id,
            case_id=case_id,
            starts_at=now + timedelta(days=2),
            office_id="demo",
        )
        first = repo.schedule_notification(
            s, case_id=case_id, kind="reminder", channel="sms", due_at=now - timedelta(minutes=1)
        )
        later = repo.schedule_notification(
            s, case_id=case_id, kind="followup", channel="sms", due_at=now + timedelta(days=3)
        )
        s.commit()

        store = SqlNotifierStore(s)
        sms = FakeSmsProvider()
        ctx = DispatchContext(
            senders=Senders(sms=sms, email=FakeEmailSender()),
            renderer=render_notification,  # type: ignore[arg-type]
            links=links,
            cipher=cipher,
            retry=no_wait_retry,
        )
        report = await dispatch_due(store, now=now, ctx=ctx)
        assert report.sent == 1 and report.ids == [first]
        assert "tra 2 giorni" in sms.sent[0].body

        found = store.find_by_phone_digest(cipher.digest(PHONE))
        assert found is not None and found[1] == case_id
        store.revoke_consents(contact_id)
        store.commit()
        report = await dispatch_due(store, now=now + timedelta(days=4), ctx=ctx)
        assert later not in report.ids or report.cancelled == 1
        assert len(sms.sent) == 1
