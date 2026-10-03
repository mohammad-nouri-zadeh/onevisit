"""Versioni finte di database e cifratura per i test del gateway (nessuna rete)."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from gateway.config import Settings
from gateway.deps import GatewayDeps
from gateway.dispatcher import RetryPolicy
from gateway.inbound import RecentIds
from gateway.personal_links import LinkBuilder
from gateway.store import ContactTarget, NotifierStore
from onevisit_channels import FakeEmailSender, FakeSmsProvider, LinkSigner, render_notification

PHONE = "+393330000000"
EMAIL = "persona@example.org"
LINK_KEY = "test-link-key"


class FakeCipher:
    """Cifratura finta e reversibile: basta per i test."""

    def encrypt(self, value: str) -> bytes:
        return b"enc:" + value.encode()

    def decrypt(self, token: bytes) -> str:
        return token.removeprefix(b"enc:").decode()

    def digest(self, value: str) -> str:
        return "hmac:" + value.replace(" ", "").lower()


@dataclass(frozen=True)
class Row:
    id: UUID
    case_id: UUID
    kind: str
    channel: str


@dataclass
class FakeStore:
    """Database in memoria con un contatto e un caso."""

    target: ContactTarget | None
    case_id: UUID
    phone_digest: str
    due: list[Row] = field(default_factory=list)
    marks: dict[UUID, str] = field(default_factory=dict)
    outcomes: list[tuple[UUID, str]] = field(default_factory=list)
    revoked: list[UUID] = field(default_factory=list)
    revoked_phones: list[str] = field(default_factory=list)
    purges: list[datetime] = field(default_factory=list)
    commits: int = 0

    def due_notifications(self, *, now: datetime, limit: int) -> Sequence[Row]:
        return [row for row in self.due if row.id not in self.marks][:limit]

    def target_for_case(self, case_id: UUID) -> ContactTarget | None:
        return self.target if case_id == self.case_id else None

    def find_by_phone_digest(self, digest: str) -> tuple[ContactTarget, UUID | None] | None:
        if self.target is None or digest != self.phone_digest:
            return None
        return self.target, self.case_id

    def mark_notification(self, notification_id: UUID, *, status: str) -> None:
        self.marks[notification_id] = status

    def revoke_consents(self, contact_id: UUID) -> None:
        self.revoked.append(contact_id)
        if self.target is not None:
            consents = dict.fromkeys(self.target.consents)
            self.target = ContactTarget(**{**self.target.__dict__, "consents": consents})

    def revoke_consents_by_phone(self, digest: str) -> None:
        self.revoked_phones.append(digest)
        if self.target is not None and digest == self.phone_digest:
            self.revoke_consents(self.target.contact_id)

    def purge_expired(self, *, now: datetime) -> int:
        self.purges.append(now)
        return 0

    def record_outcome(self, case_id: UUID, *, outcome: str) -> None:
        self.outcomes.append((case_id, outcome))

    def commit(self) -> None:
        self.commits += 1


def make_target(**overrides: Any) -> ContactTarget:
    cipher = FakeCipher()
    values: dict[str, Any] = {
        "contact_id": uuid4(),
        "email_enc": cipher.encrypt(EMAIL),
        "phone_enc": cipher.encrypt(PHONE),
        "preferred_channel": "sms",
        "fallback_channel": "email",
        "language": "it",
        "consents": {
            "reminder": "2026-10-03T10:00:00+00:00",
            "followup": "2026-10-03T10:00:00+00:00",
            "correction": None,
        },
        "confirmed": True,
        "appointment_at": datetime.now(UTC) + timedelta(days=3),
    }
    values.update(overrides)
    return ContactTarget(**values)


@pytest.fixture
def fake_store() -> FakeStore:
    return FakeStore(target=make_target(), case_id=uuid4(), phone_digest=FakeCipher().digest(PHONE))


@pytest.fixture
def links() -> LinkBuilder:
    return LinkBuilder(LinkSigner(LINK_KEY), "http://assistant.test", "http://gateway.test")


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
def no_wait_retry() -> RetryPolicy:
    return RetryPolicy(attempts=3, base_delay_s=0.0, sleep=_no_sleep)


@pytest.fixture
def make_deps(
    fake_store: FakeStore, links: LinkBuilder, no_wait_retry: RetryPolicy
) -> Callable[..., GatewayDeps]:
    def factory(**settings_overrides: Any) -> GatewayDeps:
        settings = Settings(
            database_url="",
            scheduler_enabled=False,
            link_signing_key=LINK_KEY,
            **settings_overrides,
        )

        @contextmanager
        def store_factory() -> Iterator[NotifierStore]:
            yield fake_store

        sms = FakeSmsProvider()
        factory_cm: Callable[[], AbstractContextManager[NotifierStore]] = store_factory
        return GatewayDeps(
            settings=settings,
            sms=sms,
            fake_sms=sms,
            email=FakeEmailSender(),
            links=links,
            signer=links.signer,
            cipher=FakeCipher(),
            store_factory=factory_cm,
            renderer=render_notification,  # type: ignore[arg-type]
            retry=no_wait_retry,
            recent_ids=RecentIds(100),
        )

    return factory
