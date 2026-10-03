"""Funzioni di accesso ai dati per app e librerie (storie C2, C9, C11).

Ricevono una sessione SQLAlchemy sincrona dal chiamante; non fanno commit.
Le scritture usano INSERT/UPDATE espliciti con valori calcolati in Python, senza
RETURNING, cosi' funzionano anche con ruoli che hanno solo INSERT (access_log).
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.orm import Session

from onevisit_db.errors import InvalidFieldError, NotFoundError
from onevisit_db.models import (
    AccessLog,
    Appointment,
    Case,
    CaseAnswer,
    Contact,
    Gap,
    Intervention,
    Notification,
)

Outcome = Literal["ok", "missing", "other"]
NotificationKind = Literal[
    "reminder",
    "followup",
    "followup_nudge",
    "correction_notice",
    "revocation_confirm",
    "email_confirm",
]
Channel = Literal["email", "sms"]
NotificationStatus = Literal["scheduled", "sent", "failed", "cancelled"]
GapStatus = Literal["nuova", "in-revisione", "corretta", "archiviata"]

# Campi di core.cases modificabili con update_case (mai contact_ref o esito).
UPDATABLE_CASE_FIELDS = frozenset(
    {
        "service_id",
        "variant",
        "category",
        "language",
        "office_id",
        "appointment_week",
        "deadline_days",
    }
)
# Finalita' di consenso previste per un contatto.
CONSENT_PURPOSES = ("reminder", "followup", "correction")
# Soglia k minima per le viste aggregate (C11): sotto 5 casi nessuna cella e' mostrata.
MIN_K_THRESHOLD = 5
# Invii che chiedono l'esito: inutili (e dannosi) dopo che l'esito e' stato registrato.
OUTCOME_REQUEST_KINDS = ("followup", "followup_nudge")


def _now() -> datetime:
    return datetime.now(UTC)


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)


class CaseRow(_Row):
    """Un caso letto dal database (solo campi strutturati)."""

    id: uuid.UUID
    created_at: datetime
    service_id: str
    variant: str | None
    category: str | None
    language: str
    office_id: str | None
    appointment_week: date | None
    deadline_days: int | None
    outcome: str | None
    cause: str | None
    missing_requirement_id: str | None
    closed_in_time: bool | None
    rating: int | None
    outcome_at: datetime | None
    contact_ref: uuid.UUID | None
    synthetic: bool


class ContactRow(_Row):
    """Contatto cifrato: la decifratura spetta al chiamante (ContactCipher)."""

    id: uuid.UUID
    email_enc: bytes | None
    email_hmac: str | None
    phone_enc: bytes | None
    phone_hmac: str | None
    preferred_channel: str
    fallback_channel: str | None
    language: str
    consents: dict[str, Any]
    confirmed_at: datetime | None
    expires_at: datetime
    created_at: datetime


class AppointmentRow(_Row):
    """Appuntamento esatto (schema pii)."""

    id: uuid.UUID
    contact_id: uuid.UUID
    case_id: uuid.UUID
    starts_at: datetime
    office_id: str


class NotificationRow(_Row):
    """Notifica da inviare; ``contact_ref`` arriva dal caso collegato."""

    id: uuid.UUID
    case_id: uuid.UUID
    kind: str
    channel: str
    due_at: datetime
    status: str
    attempts: int
    sent_at: datetime | None
    contact_ref: uuid.UUID | None = None


class GapRow(_Row):
    """Una lacuna con bozze e conteggi."""

    id: uuid.UUID
    service_id: str
    cause: str
    source_id: str | None
    title: str
    summary: str | None
    examples: list[Any]
    status: str
    recipient: str
    owner_ente: str | None
    requirement_id: str | None
    draft_it: str | None
    draft_easy_it: str | None
    draft_en: str | None
    case_count: int
    first_seen: datetime | None
    last_seen: datetime | None
    archived_reason: str | None
    synthetic: bool
    created_at: datetime
    updated_at: datetime


class ApprovedCorrectionRow(_Row):
    """Intervento approvato, da trasformare in ApprovedCorrection del catalogo."""

    id: uuid.UUID
    gap_id: uuid.UUID | None
    service_id: str
    requirement_id: str | None
    text_it: str
    text_easy_it: str | None
    text_en: str | None
    approved_by: str
    approved_at: datetime


class PurgeResult(_Row):
    """Esito di purge_expired: solo conteggi."""

    contacts_deleted: int
    cases_unlinked: int


class FirstVisitRateRow(_Row):
    """Riga di analytics.first_visit_rate (gruppi sotto soglia esclusi)."""

    service_id: str
    category: str | None
    language: str
    cases: int
    closed_first_visit: int
    rate: float


class WeeklyFirstVisitRow(_Row):
    """Riga di analytics.weekly_first_visit."""

    service_id: str
    week: date
    cases: int
    closed_first_visit: int
    rate: float


class GapsByCauseRow(_Row):
    """Riga di analytics.gaps_by_cause (``cases`` nullo sotto soglia)."""

    cause: str
    gaps: int
    open_gaps: int
    cases: int | None


class InterventionEffectRow(_Row):
    """Prima/dopo di un intervento; valori nulli sotto soglia."""

    intervention_id: uuid.UUID
    gap_id: uuid.UUID | None
    service_id: str
    requirement_id: str | None
    approved_at: datetime
    window_weeks: int
    cases_before: int | None
    rate_before: float | None
    cases_after: int | None
    rate_after: float | None


class AvoidedVisitsRow(_Row):
    """Stima delle visite evitate per servizio."""

    service_id: str
    interventions: int
    avoided_visits: float | None
    cost_per_slot_eur: float
    avoided_cost_eur: float | None


# ---------------------------------------------------------------- casi


def create_case(
    s: Session,
    *,
    service_id: str,
    variant: str | None,
    category: str | None,
    language: str,
    office_id: str | None,
    appointment_week: date | None,
    deadline_days: int | None,
    answers: Mapping[str, str],
    synthetic: bool = False,
) -> uuid.UUID:
    """Crea un caso con le risposte (solo id di opzione)."""
    case_id = uuid.uuid4()
    s.execute(
        insert(Case).values(
            id=case_id,
            created_at=_now(),
            service_id=service_id,
            variant=variant,
            category=category,
            language=language,
            office_id=office_id,
            appointment_week=appointment_week,
            deadline_days=deadline_days,
            synthetic=synthetic,
        )
    )
    if answers:
        s.execute(
            insert(CaseAnswer),
            [{"case_id": case_id, "question_id": q, "answer": a} for q, a in answers.items()],
        )
    return case_id


def update_case(s: Session, case_id: uuid.UUID, **fields: Any) -> None:
    """Aggiorna i campi strutturati ammessi di un caso."""
    unknown = set(fields) - UPDATABLE_CASE_FIELDS
    if unknown:
        raise InvalidFieldError(f"campi non modificabili: {sorted(unknown)}")
    if fields:
        s.execute(update(Case).where(Case.id == case_id).values(**fields))


def record_outcome(
    s: Session,
    case_id: uuid.UUID,
    *,
    outcome: Outcome,
    cause: str | None,
    missing_requirement_id: str | None,
    closed_in_time: bool | None,
    rating: int | None,
) -> None:
    """Registra l'esito dell'appuntamento."""
    s.execute(
        update(Case)
        .where(Case.id == case_id)
        .values(
            outcome=outcome,
            cause=cause,
            missing_requirement_id=missing_requirement_id,
            closed_in_time=closed_in_time,
            rating=rating,
            outcome_at=_now(),
        )
    )
    # Esito gia' noto: niente sollecito ne' follow-up che lo sovrascriverebbero (B8).
    s.execute(
        update(Notification)
        .where(
            Notification.case_id == case_id,
            Notification.status == "scheduled",
            Notification.kind.in_(OUTCOME_REQUEST_KINDS),
        )
        .values(status="cancelled")
    )


def get_case(s: Session, case_id: uuid.UUID) -> CaseRow | None:
    """Legge un caso (ruoli che possono leggere core.cases)."""
    row = s.execute(select(Case).where(Case.id == case_id)).scalar_one_or_none()
    return CaseRow.model_validate(row) if row is not None else None


def case_answers(s: Session, case_id: uuid.UUID) -> dict[str, str]:
    """Risposte di un caso, per id di domanda."""
    rows = s.execute(
        select(CaseAnswer.question_id, CaseAnswer.answer).where(CaseAnswer.case_id == case_id)
    ).all()
    return {q: a for q, a in rows}


# ---------------------------------------------------------------- contatti


def create_contact(
    s: Session,
    *,
    email_enc: bytes | None,
    email_hmac: str | None,
    phone_enc: bytes | None,
    phone_hmac: str | None,
    preferred_channel: Channel,
    fallback_channel: Channel | None,
    language: str,
    consents: Mapping[str, str | None],
    expires_at: datetime,
) -> uuid.UUID:
    """Crea un contatto gia' cifrato dal chiamante."""
    contact_id = uuid.uuid4()
    s.execute(
        insert(Contact).values(
            id=contact_id,
            email_enc=email_enc,
            email_hmac=email_hmac,
            phone_enc=phone_enc,
            phone_hmac=phone_hmac,
            preferred_channel=preferred_channel,
            fallback_channel=fallback_channel,
            language=language,
            consents=dict(consents),
            expires_at=expires_at,
            created_at=_now(),
        )
    )
    return contact_id


def get_contact(s: Session, contact_id: uuid.UUID) -> ContactRow | None:
    """Legge un contatto cifrato (solo app_assistant e app_notifier)."""
    row = s.execute(select(Contact).where(Contact.id == contact_id)).scalar_one_or_none()
    return ContactRow.model_validate(row) if row is not None else None


def confirm_contact(s: Session, contact_id: uuid.UUID) -> None:
    """Segna il contatto come confermato (doppio opt-in)."""
    s.execute(update(Contact).where(Contact.id == contact_id).values(confirmed_at=_now()))


def link_contact(s: Session, case_id: uuid.UUID, contact_id: uuid.UUID) -> None:
    """Collega un contatto a un caso tramite ``contact_ref`` (senza chiave esterna)."""
    s.execute(update(Case).where(Case.id == case_id).values(contact_ref=contact_id))


def create_appointment(
    s: Session, *, contact_id: uuid.UUID, case_id: uuid.UUID, starts_at: datetime, office_id: str
) -> uuid.UUID:
    """Registra data, ora e sede esatte nello schema pii."""
    appointment_id = uuid.uuid4()
    s.execute(
        insert(Appointment).values(
            id=appointment_id,
            contact_id=contact_id,
            case_id=case_id,
            starts_at=starts_at,
            office_id=office_id,
        )
    )
    return appointment_id


def appointment_for_case(s: Session, case_id: uuid.UUID) -> AppointmentRow | None:
    """Ultimo appuntamento registrato per un caso."""
    row = s.execute(
        select(Appointment)
        .where(Appointment.case_id == case_id)
        .order_by(Appointment.starts_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return AppointmentRow.model_validate(row) if row is not None else None


def _cancel_scheduled_for_contact(s: Session, contact_id: uuid.UUID) -> None:
    case_ids = select(Case.id).where(Case.contact_ref == contact_id).scalar_subquery()
    s.execute(
        update(Notification)
        .where(Notification.status == "scheduled", Notification.case_id.in_(case_ids))
        .values(status="cancelled")
    )


def revoke_consents(s: Session, contact_id: uuid.UUID) -> None:
    """Azzera tutti i consensi e annulla le notifiche programmate dei casi collegati."""
    current = s.execute(
        select(Contact.consents).where(Contact.id == contact_id)
    ).scalar_one_or_none()
    if current is None:
        raise NotFoundError("contatto inesistente")
    cleared = dict.fromkeys(set(CONSENT_PURPOSES) | set(current))
    s.execute(update(Contact).where(Contact.id == contact_id).values(consents=cleared))
    _cancel_scheduled_for_contact(s, contact_id)


def revoke_consents_by_phone_digest(s: Session, phone_hmac: str) -> list[uuid.UUID]:
    """Revoca i consensi di tutti i contatti con quell'HMAC del telefono (SMS STOP, B9).

    Lo stesso numero puo' stare su piu' contatti (piu' casi, piu' sessioni): STOP vale
    per tutti. Restituisce gli id dei contatti revocati.
    """
    contact_ids = list(
        s.execute(select(Contact.id).where(Contact.phone_hmac == phone_hmac)).scalars()
    )
    for contact_id in contact_ids:
        revoke_consents(s, contact_id)
    return contact_ids


def delete_contact(s: Session, contact_id: uuid.UUID) -> None:
    """Cancella contatto e appuntamenti, toglie ``contact_ref`` dai casi.

    Cancella anche le notifiche dei casi collegati: ``due_at`` e ``sent_at`` derivano
    dal giorno esatto dell'appuntamento, che non deve sopravvivere fuori da pii.
    """
    case_ids = select(Case.id).where(Case.contact_ref == contact_id).scalar_subquery()
    s.execute(delete(Notification).where(Notification.case_id.in_(case_ids)))
    s.execute(delete(Appointment).where(Appointment.contact_id == contact_id))
    s.execute(update(Case).where(Case.contact_ref == contact_id).values(contact_ref=None))
    s.execute(delete(Contact).where(Contact.id == contact_id))


def purge_expired(s: Session, *, now: datetime) -> PurgeResult:
    """Conservazione (C9): cancella i contatti scaduti, scollega i casi, mese al posto del giorno.

    Per i casi scollegati ``outcome_at`` viene troncato al primo giorno del mese.
    """
    expired = list(s.execute(select(Contact.id).where(Contact.expires_at <= now)).scalars())
    unlinked = 0
    for contact_id in expired:
        case_ids = list(s.execute(select(Case.id).where(Case.contact_ref == contact_id)).scalars())
        delete_contact(s, contact_id)
        if case_ids:
            s.execute(
                update(Case)
                .where(Case.id.in_(case_ids), Case.outcome_at.is_not(None))
                .values(outcome_at=func.date_trunc("month", Case.outcome_at))
            )
        unlinked += len(case_ids)
    return PurgeResult(contacts_deleted=len(expired), cases_unlinked=unlinked)


# ---------------------------------------------------------------- notifiche


def schedule_notification(
    s: Session, *, case_id: uuid.UUID, kind: NotificationKind, channel: Channel, due_at: datetime
) -> uuid.UUID:
    """Programma un invio (nessun testo salvato)."""
    notification_id = uuid.uuid4()
    s.execute(
        insert(Notification).values(
            id=notification_id,
            case_id=case_id,
            kind=kind,
            channel=channel,
            due_at=due_at,
            status="scheduled",
            attempts=0,
        )
    )
    return notification_id


def due_notifications(s: Session, *, now: datetime, limit: int = 50) -> list[NotificationRow]:
    """Notifiche programmate e scadute, dalla piu' vecchia."""
    rows = s.execute(
        select(
            Notification.id,
            Notification.case_id,
            Notification.kind,
            Notification.channel,
            Notification.due_at,
            Notification.status,
            Notification.attempts,
            Notification.sent_at,
            Case.contact_ref,
        )
        .join(Case, Case.id == Notification.case_id)
        .where(Notification.status == "scheduled", Notification.due_at <= now)
        .order_by(Notification.due_at, Notification.id)
        .limit(limit)
    ).mappings()
    return [NotificationRow.model_validate(dict(r)) for r in rows]


def mark_notification(
    s: Session, notification_id: uuid.UUID, *, status: NotificationStatus
) -> None:
    """Aggiorna lo stato; ``sent`` e ``failed`` contano un tentativo."""
    values: dict[str, Any] = {"status": status}
    if status in ("sent", "failed"):
        values["attempts"] = Notification.attempts + 1
    if status == "sent":
        values["sent_at"] = _now()
    s.execute(update(Notification).where(Notification.id == notification_id).values(**values))


# ---------------------------------------------------------------- lacune e interventi


def approved_corrections(s: Session) -> list[ApprovedCorrectionRow]:
    """Interventi approvati, dal piu' vecchio (overlay del catalogo)."""
    rows = s.execute(select(Intervention).order_by(Intervention.approved_at)).scalars()
    return [ApprovedCorrectionRow.model_validate(r) for r in rows]


def list_gaps(
    s: Session,
    *,
    cause: str | None = None,
    service_id: str | None = None,
    status: GapStatus | None = None,
) -> list[GapRow]:
    """Lacune filtrate, le piu' numerose e recenti prima."""
    query = select(Gap)
    if cause is not None:
        query = query.where(Gap.cause == cause)
    if service_id is not None:
        query = query.where(Gap.service_id == service_id)
    if status is not None:
        query = query.where(Gap.status == status)
    query = query.order_by(Gap.case_count.desc(), Gap.last_seen.desc().nulls_last(), Gap.id)
    return [GapRow.model_validate(g) for g in s.execute(query).scalars()]


def get_gap(s: Session, gap_id: uuid.UUID) -> GapRow | None:
    """Una lacuna per id."""
    row = s.execute(select(Gap).where(Gap.id == gap_id)).scalar_one_or_none()
    return GapRow.model_validate(row) if row is not None else None


def approve_gap(
    s: Session,
    gap_id: uuid.UUID,
    *,
    approved_by: str,
    text_it: str,
    text_easy_it: str | None,
    text_en: str | None,
) -> uuid.UUID:
    """Crea l'intervento dalla lacuna e la segna ``corretta``."""
    gap = get_gap(s, gap_id)
    if gap is None:
        raise NotFoundError("lacuna inesistente")
    now = _now()
    intervention_id = uuid.uuid4()
    s.execute(
        insert(Intervention).values(
            id=intervention_id,
            gap_id=gap_id,
            service_id=gap.service_id,
            requirement_id=gap.requirement_id,
            text_it=text_it,
            text_easy_it=text_easy_it,
            text_en=text_en,
            approved_by=approved_by,
            approved_at=now,
        )
    )
    s.execute(update(Gap).where(Gap.id == gap_id).values(status="corretta", updated_at=now))
    return intervention_id


def archive_gap(s: Session, gap_id: uuid.UUID, *, reason: str) -> None:
    """Archivia una lacuna con il motivo."""
    s.execute(
        update(Gap)
        .where(Gap.id == gap_id)
        .values(status="archiviata", archived_reason=reason, updated_at=_now())
    )


def log_access(s: Session, *, role: str, action: str, object_id: str | None) -> None:
    """Registra un accesso al pannello (ruolo dimostrativo, mai un nome)."""
    s.execute(
        insert(AccessLog).values(
            id=uuid.uuid4(), at=_now(), role=role, action=action, object_id=object_id
        )
    )


# ---------------------------------------------------------------- analytics (C11)


def _view(s: Session, sql: str) -> list[dict[str, Any]]:
    return [dict(r) for r in s.execute(text(sql)).mappings()]


def read_first_visit_rate(s: Session) -> list[FirstVisitRateRow]:
    """Tasso di chiusura al primo appuntamento per servizio, categoria e lingua."""
    rows = _view(
        s,
        "SELECT * FROM analytics.first_visit_rate ORDER BY service_id, category, language",
    )
    return [FirstVisitRateRow.model_validate(r) for r in rows]


def read_weekly_first_visit(s: Session) -> list[WeeklyFirstVisitRow]:
    """Serie settimanale per servizio."""
    rows = _view(s, "SELECT * FROM analytics.weekly_first_visit ORDER BY service_id, week")
    return [WeeklyFirstVisitRow.model_validate(r) for r in rows]


def read_gaps_by_cause(s: Session) -> list[GapsByCauseRow]:
    """Lacune per causa."""
    rows = _view(s, "SELECT * FROM analytics.gaps_by_cause ORDER BY gaps DESC, cause")
    return [GapsByCauseRow.model_validate(r) for r in rows]


def read_intervention_effect(s: Session) -> list[InterventionEffectRow]:
    """Prima e dopo ogni intervento."""
    rows = _view(s, "SELECT * FROM analytics.intervention_effect ORDER BY approved_at")
    return [InterventionEffectRow.model_validate(r) for r in rows]


def read_avoided_visits(s: Session) -> list[AvoidedVisitsRow]:
    """Stima delle visite evitate e del costo risparmiato."""
    rows = _view(s, "SELECT * FROM analytics.avoided_visits ORDER BY service_id")
    return [AvoidedVisitsRow.model_validate(r) for r in rows]


def read_config(s: Session) -> dict[str, float]:
    """Parametri delle metriche (k_threshold, cost_per_slot_eur, window_weeks)."""
    rows = s.execute(text("SELECT key, value FROM analytics.config")).all()
    return {str(k): float(v) for k, v in rows}


def set_config(s: Session, key: str, value: float) -> None:
    """Modifica un parametro esistente (pagina impostazioni della direzione)."""
    if key == "k_threshold" and value < MIN_K_THRESHOLD:
        raise InvalidFieldError(f"k_threshold non puo' essere sotto {MIN_K_THRESHOLD}")
    result = s.execute(
        text("UPDATE analytics.config SET value = :value WHERE key = :key"),
        {"key": key, "value": Decimal(str(value))},
    )
    if getattr(result, "rowcount", 0) == 0:
        raise InvalidFieldError("parametro di configurazione sconosciuto")
