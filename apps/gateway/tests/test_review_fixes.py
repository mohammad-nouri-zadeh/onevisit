"""Regressioni della revisione: STOP su tutti i contatti, purga giornaliera, chiave (B9, C9)."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from gateway.config import Settings
from gateway.deps import GatewayDeps, build_deps
from gateway.inbound import InboundContext, handle_sms
from gateway.personal_links import LinkBuilder
from gateway.scheduler import purge_once
from gateway.store import SqlNotifierStore
from onevisit_channels import FakeSmsProvider, render_notification
from onevisit_channels.errors import LinkError

from .conftest import PHONE, FakeCipher, FakeStore


def test_purge_once_runs_retention_and_commits(
    make_deps: Callable[..., GatewayDeps], fake_store: FakeStore
) -> None:
    now = datetime(2026, 10, 3, 12, tzinfo=UTC)

    purge_once(make_deps(), now=now)

    assert fake_store.purges == [now]
    assert fake_store.commits == 1


def test_gateway_refuses_to_start_without_link_key_outside_development() -> None:
    with pytest.raises(LinkError):
        build_deps(Settings(database_url="", environment="production", link_signing_key=""))


def test_gateway_and_assistant_share_the_development_key() -> None:
    from assistant_web.config import Settings as WebSettings
    from assistant_web.runtime import Runtime

    gateway = build_deps(Settings(database_url="", link_signing_key=""))
    web = Runtime(
        WebSettings(database_url="", link_signing_key=""),
        claude_client=None,
        catalog_loader=None,
        session_factory=None,
        repo=None,
        feedback_client=None,
    )
    token = gateway.signer.sign("email_confirm", "caso", "contatto")

    data = web.link_signer.verify(token, "email_confirm", max_age_s=60)
    assert (data["case_id"], data["contact_id"]) == ("caso", "contatto")


@pytest.mark.db
async def test_stop_revokes_all_contacts_sharing_the_phone(
    migrated_db_url: str, links: LinkBuilder
) -> None:
    from onevisit_db import repo

    cipher = FakeCipher()
    now = datetime.now(UTC)
    consents = {"reminder": now.isoformat(), "followup": now.isoformat(), "correction": None}
    with Session(create_engine(migrated_db_url)) as s:
        cases = []
        for _ in range(2):
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
                phone_hmac=cipher.digest(PHONE) + "-stop",
                preferred_channel="sms",
                fallback_channel=None,
                language="it",
                consents=consents,
                expires_at=now + timedelta(days=30),
            )
            repo.link_contact(s, case_id, contact_id)
            repo.schedule_notification(
                s, case_id=case_id, kind="reminder", channel="sms", due_at=now + timedelta(days=1)
            )
            cases.append(case_id)
        s.commit()

        class StopCipher(FakeCipher):
            def digest(self, value: str) -> str:
                return super().digest(value) + "-stop"

        sms = FakeSmsProvider()
        ctx = InboundContext(
            sms=sms,
            renderer=render_notification,  # type: ignore[arg-type]
            links=links,
            cipher=StopCipher(),
            assistant_base_url="http://assistant.test",
        )

        kind = await handle_sms(SqlNotifierStore(s), sender=PHONE, text="STOP", ctx=ctx)

        assert kind == "revoked"
        scheduled = s.execute(
            text(
                "SELECT count(*) FROM core.notifications WHERE case_id = ANY(:ids) "
                "AND status = 'scheduled'"
            ),
            {"ids": cases},
        ).scalar()
        assert scheduled == 0
        open_consents = s.execute(
            text(
                "SELECT count(*) FROM pii.contacts WHERE phone_hmac = :d "
                "AND consents->>'reminder' IS NOT NULL"
            ),
            {"d": cipher.digest(PHONE) + "-stop"},
        ).scalar()
        assert open_consents == 0


@pytest.mark.db
def test_purge_once_on_real_database_deletes_expired_contacts(migrated_db_url: str) -> None:
    from gateway.store import sql_store_factory
    from onevisit_db import repo

    now = datetime.now(UTC)
    engine = create_engine(migrated_db_url)
    with Session(engine) as s:
        contact_id = repo.create_contact(
            s,
            email_enc=b"enc:persona@example.org",
            email_hmac="purge-test",
            phone_enc=None,
            phone_hmac=None,
            preferred_channel="email",
            fallback_channel=None,
            language="it",
            consents={},
            expires_at=now - timedelta(days=1),
        )
        s.commit()

    from sqlalchemy.orm import sessionmaker

    deps = build_deps(Settings(database_url="", link_signing_key="k"))
    deps.store_factory = sql_store_factory(sessionmaker(engine))

    assert purge_once(deps) >= 1
    with Session(engine) as s:
        assert repo.get_contact(s, contact_id) is None
    engine.dispose()
