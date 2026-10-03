"""Dispatcher: consenso ricontrollato, tentativi, canale di riserva (C8, B7, B9)."""

from datetime import UTC, datetime
from uuid import uuid4

from gateway.dispatcher import DispatchContext, RetryPolicy, Senders, dispatch_due
from gateway.personal_links import LinkBuilder
from onevisit_channels import FakeEmailSender, FakeSmsProvider, render_notification

from .conftest import EMAIL, PHONE, FakeCipher, FakeStore, Row, make_target


def _ctx(
    sms: FakeSmsProvider, email: FakeEmailSender, links: LinkBuilder, retry: RetryPolicy
) -> DispatchContext:
    return DispatchContext(
        senders=Senders(sms=sms, email=email),
        renderer=render_notification,  # type: ignore[arg-type]
        links=links,
        cipher=FakeCipher(),
        retry=retry,
    )


async def test_reminder_is_sent_by_sms_with_personal_link(
    fake_store: FakeStore, links: LinkBuilder, no_wait_retry: RetryPolicy
) -> None:
    row = Row(uuid4(), fake_store.case_id, "reminder", "sms")
    fake_store.due.append(row)
    sms, email = FakeSmsProvider(), FakeEmailSender()

    report = await dispatch_due(
        fake_store, now=datetime.now(UTC), ctx=_ctx(sms, email, links, no_wait_retry)
    )

    assert report.sent == 1
    assert fake_store.marks[row.id] == "sent"
    assert sms.sent[0].to == PHONE
    assert "http://assistant.test/c/" in sms.sent[0].body


async def test_revoked_consent_cancels_without_sending(
    fake_store: FakeStore, links: LinkBuilder, no_wait_retry: RetryPolicy
) -> None:
    fake_store.target = make_target(
        consents={"reminder": None, "followup": None, "correction": None}
    )
    row = Row(uuid4(), fake_store.case_id, "reminder", "sms")
    fake_store.due.append(row)
    sms, email = FakeSmsProvider(), FakeEmailSender()

    await dispatch_due(
        fake_store, now=datetime.now(UTC), ctx=_ctx(sms, email, links, no_wait_retry)
    )

    assert fake_store.marks[row.id] == "cancelled"
    assert sms.attempts == 0
    assert email.attempts == 0


async def test_deleted_contact_cancels(
    fake_store: FakeStore, links: LinkBuilder, no_wait_retry: RetryPolicy
) -> None:
    fake_store.target = None
    row = Row(uuid4(), fake_store.case_id, "followup", "sms")
    fake_store.due.append(row)

    await dispatch_due(
        fake_store,
        now=datetime.now(UTC),
        ctx=_ctx(FakeSmsProvider(), FakeEmailSender(), links, no_wait_retry),
    )

    assert fake_store.marks[row.id] == "cancelled"


async def test_primary_fails_three_times_then_fallback_is_used(
    fake_store: FakeStore, links: LinkBuilder
) -> None:
    delays: list[float] = []

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    retry = RetryPolicy(attempts=3, base_delay_s=1.0, sleep=record_sleep)
    row = Row(uuid4(), fake_store.case_id, "followup", "sms")
    fake_store.due.append(row)
    sms, email = FakeSmsProvider(always_fail=True), FakeEmailSender()

    report = await dispatch_due(
        fake_store, now=datetime.now(UTC), ctx=_ctx(sms, email, links, retry)
    )

    assert sms.attempts == 3
    assert delays == [1.0, 2.0]
    assert report.sent == 1
    assert email.sent[0].to == EMAIL
    assert "http://gateway.test/r/" in email.sent[0].text
    assert email.sent[0].unsubscribe_url.startswith("http://assistant.test/consents/")


async def test_both_channels_fail_marks_failed_without_leaking(
    fake_store: FakeStore, links: LinkBuilder, no_wait_retry: RetryPolicy, caplog: object
) -> None:
    row = Row(uuid4(), fake_store.case_id, "reminder", "sms")
    fake_store.due.append(row)
    sms, email = FakeSmsProvider(always_fail=True), FakeEmailSender(always_fail=True)

    report = await dispatch_due(
        fake_store, now=datetime.now(UTC), ctx=_ctx(sms, email, links, no_wait_retry)
    )

    assert report.failed == 1
    assert fake_store.marks[row.id] == "failed"
    assert sms.attempts == 3
    assert email.attempts == 3
    log_text = getattr(caplog, "text", "")
    assert PHONE not in log_text
    assert EMAIL not in log_text


async def test_unconfirmed_email_is_not_used(
    fake_store: FakeStore, links: LinkBuilder, no_wait_retry: RetryPolicy
) -> None:
    fake_store.target = make_target(
        preferred_channel="email", fallback_channel=None, confirmed=False
    )
    row = Row(uuid4(), fake_store.case_id, "reminder", "email")
    fake_store.due.append(row)
    email = FakeEmailSender()

    await dispatch_due(
        fake_store, now=datetime.now(UTC), ctx=_ctx(FakeSmsProvider(), email, links, no_wait_retry)
    )

    assert fake_store.marks[row.id] == "cancelled"
    assert email.attempts == 0
