"""Finti per i test di assistant_web: repo in memoria, sessioni, impostazioni (B1-B9).

Dati solo sintetici; nessuna chiamata di rete.
"""

import base64
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from assistant_web.config import Settings
from assistant_web.main import create_app
from onevisit_agent.testing import FakeClaudeClient

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
FAKE_KEY = base64.b64encode(b"\x01" * 32).decode()
FAKE_HMAC = base64.b64encode(b"\x02" * 32).decode()


@dataclass
class FakeCase:
    """Riga di caso minima, come ``CaseRow``."""

    id: uuid.UUID
    service_id: str
    language: str


@dataclass
class FakeContact:
    """Riga di contatto minima, come ``ContactRow``."""

    id: uuid.UUID
    language: str
    consents: dict[str, str | None]
    confirmed_at: datetime | None = None


@dataclass
class FakeAppointment:
    """Riga di appuntamento minima."""

    starts_at: datetime


@dataclass
class FakeRepo:
    """Repo in memoria che registra ogni chiamata con i suoi argomenti."""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    cases: dict[uuid.UUID, FakeCase] = field(default_factory=dict)
    answers: dict[uuid.UUID, dict[str, str]] = field(default_factory=dict)
    contacts: dict[uuid.UUID, FakeContact] = field(default_factory=dict)
    appointments: dict[uuid.UUID, FakeAppointment] = field(default_factory=dict)

    def _log(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def create_case(self, s: object, **kw: Any) -> uuid.UUID:
        self._log("create_case", **kw)
        case_id = uuid.uuid4()
        self.cases[case_id] = FakeCase(case_id, kw["service_id"], kw["language"])
        self.answers[case_id] = dict(kw["answers"])
        return case_id

    def add_case(self, service_id: str, language: str, answers: dict[str, str]) -> uuid.UUID:
        case_id = uuid.uuid4()
        self.cases[case_id] = FakeCase(case_id, service_id, language)
        self.answers[case_id] = answers
        return case_id

    def update_case(self, s: object, case_id: uuid.UUID, **kw: Any) -> None:
        self._log("update_case", case_id=case_id, **kw)

    def get_case(self, s: object, case_id: uuid.UUID) -> FakeCase | None:
        return self.cases.get(case_id)

    def case_answers(self, s: object, case_id: uuid.UUID) -> dict[str, str]:
        return self.answers.get(case_id, {})

    def record_outcome(self, s: object, case_id: uuid.UUID, **kw: Any) -> None:
        self._log("record_outcome", case_id=case_id, **kw)

    def create_contact(self, s: object, **kw: Any) -> uuid.UUID:
        self._log("create_contact", **kw)
        contact_id = uuid.uuid4()
        self.contacts[contact_id] = FakeContact(contact_id, kw["language"], dict(kw["consents"]))
        return contact_id

    def get_contact(self, s: object, contact_id: uuid.UUID) -> FakeContact | None:
        return self.contacts.get(contact_id)

    def confirm_contact(self, s: object, contact_id: uuid.UUID) -> None:
        self._log("confirm_contact", contact_id=contact_id)
        self.contacts[contact_id].confirmed_at = datetime.now(UTC)

    def create_appointment(self, s: object, **kw: Any) -> uuid.UUID:
        self._log("create_appointment", **kw)
        self.appointments[kw["case_id"]] = FakeAppointment(kw["starts_at"])
        return uuid.uuid4()

    def appointment_for_case(self, s: object, case_id: uuid.UUID) -> FakeAppointment | None:
        return self.appointments.get(case_id)

    def link_contact(self, s: object, case_id: uuid.UUID, contact_id: uuid.UUID) -> None:
        self._log("link_contact", case_id=case_id, contact_id=contact_id)

    def schedule_notification(self, s: object, **kw: Any) -> uuid.UUID:
        self._log("schedule_notification", **kw)
        return uuid.uuid4()

    def revoke_consents(self, s: object, contact_id: uuid.UUID) -> None:
        self._log("revoke_consents", contact_id=contact_id)

    def delete_contact(self, s: object, contact_id: uuid.UUID) -> None:
        self._log("delete_contact", contact_id=contact_id)

    def approved_corrections(self, s: object) -> list[Any]:
        return []


class FakeSession:
    """Sessione finta: commit e rollback non fanno nulla."""

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


def make_settings(**overrides: Any) -> Settings:
    """Impostazioni di test: dati del repository, chiavi finte, nessuna chiave API."""
    values: dict[str, Any] = {
        "data_dir": DATA_DIR,
        "anthropic_api_key": "",
        "encryption_key": FAKE_KEY,
        "hmac_key": FAKE_HMAC,
        "link_signing_key": "test-link-key",
        "session_secret": "test-session-secret",
        "database_url": "",
        "public_base_url": "http://testserver",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def settings_factory() -> Callable[..., Settings]:
    """La funzione make_settings, per i test che costruiscono l'app da soli."""
    return make_settings


@pytest.fixture
def fake_repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def make_client(fake_repo: FakeRepo) -> Callable[..., TestClient]:
    """Costruisce un TestClient con client Claude finto e repo finto."""

    def build(
        claude: FakeClaudeClient | None = None, *, with_db: bool = True, **overrides: Any
    ) -> TestClient:
        app = create_app(
            make_settings(**overrides),
            claude_client=claude,
            session_factory=FakeSession if with_db else None,
            repo=fake_repo,
        )
        return TestClient(app, raise_server_exceptions=False)

    return build
