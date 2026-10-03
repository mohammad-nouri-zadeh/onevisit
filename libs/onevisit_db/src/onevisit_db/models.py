"""Modelli SQLAlchemy 2 delle tabelle di core, pii e analytics (storie C2, C11).

Lo schema reale nasce dalla migrazione 0002 (SQL esplicito); questi modelli servono
al codice applicativo e come ``target_metadata`` di Alembic. Ogni tabella ha lo schema
esplicito. ``core.cases.contact_ref`` non ha chiave esterna verso ``pii`` di proposito.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base dichiarativa con convenzione di nomi stabile per vincoli e indici."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


TZ = DateTime(timezone=True)


class Case(Base):
    """Un caso: solo campi strutturati, nessun testo libero."""

    __tablename__ = "cases"
    __table_args__ = ({"schema": "core"},)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(TZ)
    service_id: Mapped[str] = mapped_column(Text)
    variant: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    office_id: Mapped[str | None] = mapped_column(Text)
    appointment_week: Mapped[date | None] = mapped_column(Date)
    deadline_days: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(Text)
    cause: Mapped[str | None] = mapped_column(Text)
    missing_requirement_id: Mapped[str | None] = mapped_column(Text)
    closed_in_time: Mapped[bool | None] = mapped_column(Boolean)
    rating: Mapped[int | None] = mapped_column(Integer)
    outcome_at: Mapped[datetime | None] = mapped_column(TZ)
    contact_ref: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class CaseAnswer(Base):
    """Risposta a una domanda decisiva: solo l'id dell'opzione."""

    __tablename__ = "case_answers"
    __table_args__ = ({"schema": "core"},)

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.cases.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[str] = mapped_column(Text, primary_key=True)
    answer: Mapped[str] = mapped_column(Text)


class Gap(Base):
    """Una lacuna: gruppo di esiti negativi con la stessa causa."""

    __tablename__ = "gaps"
    __table_args__ = ({"schema": "core"},)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_id: Mapped[str] = mapped_column(Text)
    cause: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    examples: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(Text, default="nuova")
    recipient: Mapped[str] = mapped_column(Text)
    owner_ente: Mapped[str | None] = mapped_column(Text)
    requirement_id: Mapped[str | None] = mapped_column(Text)
    draft_it: Mapped[str | None] = mapped_column(Text)
    draft_easy_it: Mapped[str | None] = mapped_column(Text)
    draft_en: Mapped[str | None] = mapped_column(Text)
    case_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen: Mapped[datetime | None] = mapped_column(TZ)
    last_seen: Mapped[datetime | None] = mapped_column(TZ)
    archived_reason: Mapped[str | None] = mapped_column(Text)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TZ)
    updated_at: Mapped[datetime] = mapped_column(TZ)


class GapCase(Base):
    """Collegamento tra lacuna e caso."""

    __tablename__ = "gap_cases"
    __table_args__ = ({"schema": "core"},)

    gap_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.gaps.id", ondelete="CASCADE"), primary_key=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.cases.id", ondelete="CASCADE"), primary_key=True
    )


class Intervention(Base):
    """Correzione approvata nel pannello; ``approved_by`` e' un ruolo, mai un nome."""

    __tablename__ = "interventions"
    __table_args__ = ({"schema": "core"},)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gap_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("core.gaps.id", ondelete="SET NULL")
    )
    service_id: Mapped[str] = mapped_column(Text)
    requirement_id: Mapped[str | None] = mapped_column(Text)
    text_it: Mapped[str] = mapped_column(Text)
    text_easy_it: Mapped[str | None] = mapped_column(Text)
    text_en: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str] = mapped_column(Text)
    approved_at: Mapped[datetime] = mapped_column(TZ)


class Notification(Base):
    """Stato di un invio programmato. Nessun testo."""

    __tablename__ = "notifications"
    __table_args__ = ({"schema": "core"},)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("core.cases.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(TZ)
    status: Mapped[str] = mapped_column(Text, default="scheduled")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(TZ)


class AccessLog(Base):
    """Registro degli accessi al pannello: ruolo, azione, id opaco."""

    __tablename__ = "access_log"
    __table_args__ = ({"schema": "core"},)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    at: Mapped[datetime] = mapped_column(TZ)
    role: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    object_id: Mapped[str | None] = mapped_column(Text)


class Contact(Base):
    """Contatto cifrato (AES-256-GCM) con impronte HMAC per la ricerca."""

    __tablename__ = "contacts"
    __table_args__ = ({"schema": "pii"},)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    email_hmac: Mapped[str | None] = mapped_column(Text)
    phone_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    phone_hmac: Mapped[str | None] = mapped_column(Text)
    preferred_channel: Mapped[str] = mapped_column(Text)
    fallback_channel: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    consents: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    confirmed_at: Mapped[datetime | None] = mapped_column(TZ)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    created_at: Mapped[datetime] = mapped_column(TZ)


class Appointment(Base):
    """Data, ora e sede esatte dell'appuntamento; le usa solo lo scheduler."""

    __tablename__ = "appointments"
    __table_args__ = ({"schema": "pii"},)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("pii.contacts.id", ondelete="CASCADE")
    )
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    starts_at: Mapped[datetime] = mapped_column(TZ)
    office_id: Mapped[str] = mapped_column(Text)


class AnalyticsConfig(Base):
    """Parametri delle metriche, modificabili dal ruolo direzione."""

    __tablename__ = "config"
    __table_args__ = ({"schema": "analytics"},)

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric)


metadata = Base.metadata
