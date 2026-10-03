"""Accesso ai dati del notificatore (storie C8, B6, B9).

``NotifierStore`` e' il confine verso il database: il dispatcher e il webhook lo usano
senza sapere di SQL, e nei test lo si sostituisce con una versione in memoria.
``SqlNotifierStore`` usa le funzioni di ``onevisit_db.repo`` (docs/contracts.md, sezione 4)
e due letture SQL per trovare il contatto, non previste dal contratto.
"""

import importlib
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker


class DueNotification(Protocol):
    """Riga di ``core.notifications`` in scadenza (vedi ``NotificationRow``)."""

    @property
    def id(self) -> UUID: ...
    @property
    def case_id(self) -> UUID: ...
    @property
    def kind(self) -> str: ...
    @property
    def channel(self) -> str: ...


@dataclass(frozen=True)
class ContactTarget:
    """Contatto cifrato collegato a un caso, con i consensi e l'ora dell'appuntamento."""

    contact_id: UUID
    email_enc: bytes | None
    phone_enc: bytes | None
    preferred_channel: str
    fallback_channel: str | None
    language: str
    consents: Mapping[str, str | None]
    confirmed: bool
    appointment_at: datetime | None


class NotifierStore(Protocol):
    """Operazioni sul database usate dal gateway."""

    def due_notifications(self, *, now: datetime, limit: int) -> Sequence[DueNotification]: ...
    def target_for_case(self, case_id: UUID) -> ContactTarget | None: ...
    def find_by_phone_digest(self, digest: str) -> tuple[ContactTarget, UUID | None] | None: ...
    def mark_notification(self, notification_id: UUID, *, status: str) -> None: ...
    def revoke_consents(self, contact_id: UUID) -> None: ...
    def revoke_consents_by_phone(self, digest: str) -> None: ...
    def purge_expired(self, *, now: datetime) -> int: ...
    def record_outcome(self, case_id: UUID, *, outcome: str) -> None: ...
    def commit(self) -> None: ...


_TARGET_FOR_CASE = text(
    "SELECT c.id, c.email_enc, c.phone_enc, c.preferred_channel, c.fallback_channel, c.language, "
    "c.consents, c.confirmed_at, (SELECT a.starts_at FROM pii.appointments a "
    "WHERE a.contact_id = c.id ORDER BY a.starts_at DESC LIMIT 1) AS starts_at "
    "FROM core.cases k JOIN pii.contacts c ON c.id = k.contact_ref WHERE k.id = :case_id"
)
_FIND_BY_PHONE = text(
    "SELECT c.id, c.email_enc, c.phone_enc, c.preferred_channel, c.fallback_channel, c.language, "
    "c.consents, c.confirmed_at, (SELECT a.starts_at FROM pii.appointments a "
    "WHERE a.contact_id = c.id ORDER BY a.starts_at DESC LIMIT 1) AS starts_at, "
    "(SELECT k.id FROM core.cases k WHERE k.contact_ref = c.id "
    "ORDER BY k.created_at DESC LIMIT 1) AS case_id "
    "FROM pii.contacts c WHERE c.phone_hmac = :digest "
    # Piu' contatti possono avere lo stesso numero: si sceglie il piu' recente, in modo
    # deterministico, cosi' 1/2/3 va sempre al caso dell'ultima conversazione.
    "ORDER BY c.created_at DESC, c.id LIMIT 1"
)

# Esiti registrati come i pulsanti del web: 1 fatto, 2 mancava qualcosa, 3 altro.
_CLOSED_IN_TIME = {"ok": True, "missing": False, "other": None}


def _to_bytes(value: Any) -> bytes | None:
    return bytes(value) if value is not None else None


def _row_to_target(row: Any) -> ContactTarget:
    consents = row.consents if isinstance(row.consents, dict) else {}
    return ContactTarget(
        contact_id=row.id,
        email_enc=_to_bytes(row.email_enc),
        phone_enc=_to_bytes(row.phone_enc),
        preferred_channel=str(row.preferred_channel),
        fallback_channel=row.fallback_channel,
        language=str(row.language or "it"),
        consents=consents,
        confirmed=row.confirmed_at is not None,
        appointment_at=row.starts_at,
    )


class SqlNotifierStore:
    """Implementazione su PostgreSQL tramite ``onevisit_db.repo``."""

    def __init__(self, session: Session) -> None:
        self._session = session
        # Import ritardato: onevisit_db.repo e' scritto in parallelo da un altro gruppo.
        self._repo: Any = importlib.import_module("onevisit_db.repo")

    def due_notifications(self, *, now: datetime, limit: int) -> Sequence[DueNotification]:
        """Notifiche programmate con ``due_at <= now``."""
        rows: Sequence[DueNotification] = self._repo.due_notifications(
            self._session, now=now, limit=limit
        )
        return rows

    def target_for_case(self, case_id: UUID) -> ContactTarget | None:
        """Contatto collegato al caso, se esiste ancora."""
        row = self._session.execute(_TARGET_FOR_CASE, {"case_id": case_id}).first()
        return _row_to_target(row) if row is not None else None

    def find_by_phone_digest(self, digest: str) -> tuple[ContactTarget, UUID | None] | None:
        """Contatto con quell'HMAC del telefono e il suo caso piu' recente."""
        row = self._session.execute(_FIND_BY_PHONE, {"digest": digest}).first()
        if row is None:
            return None
        return _row_to_target(row), row.case_id

    def mark_notification(self, notification_id: UUID, *, status: str) -> None:
        """Aggiorna lo stato della notifica."""
        self._repo.mark_notification(self._session, notification_id, status=status)

    def revoke_consents(self, contact_id: UUID) -> None:
        """Azzera i consensi e annulla le notifiche programmate."""
        self._repo.revoke_consents(self._session, contact_id)

    def revoke_consents_by_phone(self, digest: str) -> None:
        """SMS STOP: revoca i consensi di tutti i contatti con quel numero (B9)."""
        self._repo.revoke_consents_by_phone_digest(self._session, digest)

    def purge_expired(self, *, now: datetime) -> int:
        """Conservazione (C9): cancella i contatti scaduti; restituisce quanti."""
        result = self._repo.purge_expired(self._session, now=now)
        return int(result.contacts_deleted)

    def record_outcome(self, case_id: UUID, *, outcome: str) -> None:
        """Registra l'esito come il pulsante corrispondente del web."""
        self._repo.record_outcome(
            self._session,
            case_id,
            outcome=outcome,
            cause=None,
            missing_requirement_id=None,
            closed_in_time=_CLOSED_IN_TIME.get(outcome),
            rating=None,
        )

    def commit(self) -> None:
        """Conferma la transazione."""
        self._session.commit()


def sql_store_factory(sessions: sessionmaker[Session]) -> Any:
    """Factory di context manager: apre una sessione e restituisce un ``SqlNotifierStore``."""

    @contextmanager
    def factory() -> Iterator[NotifierStore]:
        with sessions() as session:
            yield SqlNotifierStore(session)

    return factory
