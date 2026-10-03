"""Contatto facoltativo dopo l'appuntamento, consensi separati e conferma email (storia B5).

Il contatto viene cifrato con ``ContactCipher`` e salvato solo nello schema ``pii``.
Per l'email si programma prima la conferma; le altre notifiche partono dopo ``/confirm``.
"""

import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.exc import SQLAlchemyError

from assistant_web.runtime import Runtime
from assistant_web.sessions import ChatSession
from assistant_web.web import TEMPLATES, context, runtime, session_id_from_cookie
from onevisit_agent import AppointmentInfo
from onevisit_channels import (
    PURPOSE_CHECKLIST,
    PURPOSE_CONSENTS,
    PURPOSE_EMAIL_CONFIRM,
    LinkError,
    informativa,
    normalize_phone,
    plan_notifications,
)
from onevisit_privacy import PrivacyError

logger = logging.getLogger(__name__)
router = APIRouter()
ROME = ZoneInfo("Europe/Rome")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
CONSENT_KEYS = ("reminder", "followup", "correction")
# Ufficio usato quando il cittadino non ha indicato la sede.
UNKNOWN_OFFICE = "non-indicata"
Channel = Literal["email", "sms"]


def _form_error(request: Request, language: str, key: str) -> Response:
    return TEMPLATES.TemplateResponse(
        request,
        "partials/contact.html",
        context(language, error_key=key, informativa=informativa(language)),
        status_code=422,
    )


def schedule_followups(
    rt: Runtime,
    s: object,
    *,
    case_id: UUID,
    channel: Channel,
    appointment_at: datetime,
    consents: dict[str, str | None],
) -> None:
    """Programma promemoria e follow-up secondo i consensi (tempi compressi in demo)."""
    seconds = rt.settings.demo_seconds_per_day if rt.settings.demo_mode else None
    plan = plan_notifications(
        appointment_at=appointment_at,
        now=datetime.now(UTC),
        reminder_days_before=rt.settings.reminder_days_before,
        seconds_per_day=seconds,
    )
    for kind, due_at in plan:
        purpose = "reminder" if kind == "reminder" else "followup"
        if consents.get(purpose):
            rt.repo.schedule_notification(
                s, case_id=case_id, kind=kind, channel=channel, due_at=due_at
            )


def _monday(day: date) -> date:
    """Lunedi' della settimana: in core va solo la settimana, mai il giorno esatto."""
    return day - timedelta(days=day.weekday())


def _ensure_case(rt: Runtime, s: object, chat: ChatSession) -> UUID:
    """Caso esistente o creato ora con i soli campi strutturati."""
    if chat.case_id is not None:
        return chat.case_id
    state = chat.state
    case_id: UUID = rt.repo.create_case(
        s,
        service_id=state.case.service_id or "non-identificato",
        variant=state.case.variant,
        category=state.case.category,
        language=state.language,
        office_id=state.case.appointment.office_id if state.case.appointment else None,
        appointment_week=_monday(state.case.appointment.date) if state.case.appointment else None,
        deadline_days=state.case.deadline_days,
        answers=dict(state.case.answers),
    )
    return case_id


@router.post("/contact", response_class=HTMLResponse)
def contact(
    request: Request,
    choice: Annotated[str, Form()] = "none",
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    primary: Annotated[str, Form()] = "email",
    consent_reminder: Annotated[str | None, Form()] = None,
    consent_followup: Annotated[str | None, Form()] = None,
    consent_correction: Annotated[str | None, Form()] = None,
) -> Response:
    """Salva il contatto cifrato, l'appuntamento e programma le notifiche."""
    rt = runtime(request)
    chat = rt.sessions.peek(session_id_from_cookie(request))
    if chat is None or chat.state.case.appointment is None:
        return Response(status_code=404)
    language = chat.state.language
    if choice not in ("email", "sms", "both"):
        return TEMPLATES.TemplateResponse(
            request, "partials/contact_done.html", context(language, result="none")
        )
    use_email = choice in ("email", "both")
    use_sms = choice in ("sms", "both")
    if use_email and not EMAIL_RE.match(email.strip()):
        return _form_error(request, language, "invalid_email")
    phone_e164: str | None = None
    if use_sms:
        try:
            phone_e164 = normalize_phone(phone)
        except ValueError:
            return _form_error(request, language, "invalid_phone")
    preferred: Channel = "email" if use_email else "sms"
    if choice == "both" and primary == "sms":
        preferred = "sms"
    fallback: Channel | None = None
    if choice == "both":
        fallback = "sms" if preferred == "email" else "email"
    now_iso = datetime.now(UTC).isoformat()
    flags = {
        "reminder": consent_reminder,
        "followup": consent_followup,
        "correction": consent_correction,
    }
    consents = {k: (now_iso if flags[k] else None) for k in CONSENT_KEYS}
    if not any(consents.values()):
        # Nessuna finalita' scelta: nessuna base per conservare email o telefono.
        return TEMPLATES.TemplateResponse(
            request, "partials/contact_done.html", context(language, result="none")
        )
    appointment = chat.state.case.appointment
    if not rt.db_enabled:
        return _form_error(request, language, "error_db")
    try:
        links = _save_contact(
            rt,
            chat=chat,
            email=email.strip() if use_email else None,
            phone=phone_e164,
            preferred=preferred,
            fallback=fallback,
            consents=consents,
            appointment=appointment,
        )
    except (SQLAlchemyError, PrivacyError) as exc:
        logger.warning("contatto non salvato: %s", type(exc).__name__)
        return _form_error(request, language, "error_db")
    chat.contact_saved = True
    return TEMPLATES.TemplateResponse(
        request,
        "partials/contact_done.html",
        context(language, result=preferred, **links),
    )


def _save_contact(
    rt: Runtime,
    *,
    chat: ChatSession,
    email: str | None,
    phone: str | None,
    preferred: Channel,
    fallback: Channel | None,
    consents: dict[str, str | None],
    appointment: AppointmentInfo,
) -> dict[str, str]:
    """Scrive contatto, appuntamento e notifiche in una transazione; restituisce i link."""
    cipher = rt.cipher()
    starts_at = datetime.combine(appointment.date, appointment.time, tzinfo=ROME)
    expires_at = starts_at + timedelta(days=rt.settings.contact_retention_days)
    with rt.db() as s:
        case_id = _ensure_case(rt, s, chat)
        chat.case_id = case_id
        # Sede e settimana sul caso anche se era stato creato prima dell'appuntamento.
        rt.repo.update_case(
            s,
            case_id,
            office_id=appointment.office_id,
            appointment_week=_monday(appointment.date),
        )
        if chat.contact_id is not None:
            # Modulo inviato di nuovo: il contatto precedente (e le sue notifiche) sparisce,
            # cosi' non restano contatti orfani con lo stesso numero o indirizzo.
            rt.repo.delete_contact(s, chat.contact_id)
            chat.contact_id = None
        contact_id: UUID = rt.repo.create_contact(
            s,
            email_enc=cipher.encrypt(email) if email else None,
            email_hmac=cipher.digest(email) if email else None,
            phone_enc=cipher.encrypt(phone) if phone else None,
            phone_hmac=cipher.digest(phone) if phone else None,
            preferred_channel=preferred,
            fallback_channel=fallback,
            language=chat.state.language,
            consents=consents,
            expires_at=expires_at,
        )
        rt.repo.create_appointment(
            s,
            contact_id=contact_id,
            case_id=case_id,
            starts_at=starts_at,
            office_id=appointment.office_id or UNKNOWN_OFFICE,
        )
        rt.repo.link_contact(s, case_id, contact_id)
        chat.contact_id = contact_id
        if email:
            # Anche l'email di riserva (scelta "entrambi" con SMS principale) va confermata,
            # altrimenti non sarebbe mai utilizzabile.
            rt.repo.schedule_notification(
                s, case_id=case_id, kind="email_confirm", channel="email", due_at=datetime.now(UTC)
            )
        if preferred == "sms":
            schedule_followups(
                rt,
                s,
                case_id=case_id,
                channel=preferred,
                appointment_at=starts_at,
                consents=consents,
            )
    signer = rt.link_signer
    base = rt.settings.public_base_url.rstrip("/")
    return {
        "checklist_url": f"{base}/c/{signer.sign(PURPOSE_CHECKLIST, case_id)}",
        "consents_url": f"{base}/consents/{signer.sign(PURPOSE_CONSENTS, case_id, contact_id)}",
        "confirm_url": f"{base}/confirm/{signer.sign(PURPOSE_EMAIL_CONFIRM, case_id, contact_id)}",
    }


@router.get("/confirm/{token}", response_class=HTMLResponse)
def confirm_email(request: Request, token: str) -> Response:
    """Conferma dell'indirizzo email: solo ora si programmano promemoria e follow-up."""
    rt = runtime(request)
    max_age = rt.settings.link_max_age_days * 86_400
    try:
        data = rt.link_signer.verify(token, PURPOSE_EMAIL_CONFIRM, max_age)
    except LinkError:
        return TEMPLATES.TemplateResponse(
            request, "message.html", context("it", key="error_link"), status_code=404
        )
    case_id = UUID(str(data["case_id"]))
    contact_id = UUID(str(data["contact_id"])) if data["contact_id"] else None
    if contact_id is None or not rt.db_enabled:
        return Response(status_code=404)
    with rt.db() as s:
        contact_row = rt.repo.get_contact(s, contact_id)
        appointment = rt.repo.appointment_for_case(s, case_id)
        if contact_row is None or appointment is None:
            return Response(status_code=404)
        language = contact_row.language
        primary_is_email = getattr(contact_row, "preferred_channel", "email") == "email"
        first_confirmation = contact_row.confirmed_at is None
        if first_confirmation:
            rt.repo.confirm_contact(s, contact_id)
        # Con SMS principale gli invii sono gia' programmati: la conferma rende solo
        # utilizzabile l'email di riserva.
        if first_confirmation and primary_is_email:
            schedule_followups(
                rt,
                s,
                case_id=case_id,
                channel="email",
                appointment_at=appointment.starts_at,
                consents=dict(contact_row.consents),
            )
    return TEMPLATES.TemplateResponse(
        request, "message.html", context(language, key="confirm_done")
    )
