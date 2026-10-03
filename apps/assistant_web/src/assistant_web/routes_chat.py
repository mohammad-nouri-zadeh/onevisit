"""Rotte della chat del cittadino: benvenuto, turno, eventi, promemoria .ics (B1-B4).

Il messaggio passa da ``redact`` prima di arrivare all'agente; nel database finiscono
solo campi strutturati del caso (mai testo libero).
"""

import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.exc import SQLAlchemyError

from assistant_web.i18n import messages, ui_language
from assistant_web.render import render_markdown
from assistant_web.runtime import Runtime
from assistant_web.sessions import ChatSession
from assistant_web.web import (
    COOKIE_NAME,
    TEMPLATES,
    context,
    request_language,
    runtime,
    session_id_from_cookie,
    signed_session_cookie,
)
from onevisit_agent import Capabilities, TurnResult, fallback_message
from onevisit_channels import informativa
from onevisit_knowledge import KnowledgeError
from onevisit_privacy import redact

logger = logging.getLogger(__name__)
router = APIRouter()
ROME = ZoneInfo("Europe/Rome")
# Durata indicativa dell'appuntamento nel file .ics, in minuti.
ICS_DURATION_MIN = 30


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    """Pagina della chat con il benvenuto nella lingua scelta o del browser."""
    language = request_language(request)
    return TEMPLATES.TemplateResponse(request, "index.html", context(language))


def _run_turn(rt: Runtime, chat: ChatSession, text: str, language: str) -> TurnResult:
    """Turno dell'agente, o messaggio di cortesia se l'agente non e' disponibile."""
    agent = rt.agent()
    if agent is None:
        # Senza agente nessuno ha ancora scelto la lingua: vale quella del browser,
        # come farebbe l'agente prima della sua prima risposta.
        if not chat.state.history:
            chat.state.language = language
        reply = fallback_message(chat.state.language, rt.settings.official_fallback_url)
        return TurnResult(messages=[reply], language=chat.state.language, state=chat.state)
    capabilities = Capabilities(channel="web", buttons=True, browser_language=language)
    return agent.run_turn(chat.state, text, capabilities)


# Servizio fittizio per le richieste fuori catalogo (B1): il caso resta strutturato e
# l'analisi lo raggruppa come lacuna "procedura-mancante".
MISSING_PROCEDURE_SERVICE_ID = "non-in-catalogo"
MISSING_PROCEDURE_CAUSE = "procedura-mancante"
# Esito -> chiuso nei tempi, come i pulsanti della pagina esito e le risposte SMS 1/2/3.
CLOSED_IN_TIME = {"ok": True, "missing": False, "other": None}
OUTCOMES = frozenset(CLOSED_IN_TIME)


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _handle_events(rt: Runtime, chat: ChatSession, result: TurnResult) -> bool:
    """Applica gli eventi strutturati; restituisce vero se va mostrato il modulo contatti."""
    show_contact = False
    case = result.state.case
    for event in result.events:
        if event.kind == "missing_procedure":
            if not chat.missing_procedure:
                _record_missing_procedure(rt, result)
            chat.missing_procedure = True
        elif event.kind == "outcome_recorded":
            _record_outcome(rt, chat, result, event.data)
        elif event.kind == "case_confirmed" and chat.case_id is None and case.service_id:
            chat.case_id = _create_case(rt, chat, result)
        elif event.kind == "appointment_recorded" and case.appointment is not None:
            show_contact = not chat.contact_saved
            _record_appointment_week(rt, chat, result)
    return show_contact


def _create_case(rt: Runtime, chat: ChatSession, result: TurnResult) -> UUID | None:
    """Crea il caso con i soli campi strutturati; ``None`` se il database non c'e'."""
    case = result.state.case
    if not rt.db_enabled or case.service_id is None:
        return None
    # L'appuntamento puo' arrivare prima della conferma: sede e settimana subito sul caso.
    appointment = case.appointment
    try:
        with rt.db() as s:
            case_id: UUID = rt.repo.create_case(
                s,
                service_id=case.service_id,
                variant=case.variant,
                category=case.category,
                language=result.language,
                office_id=appointment.office_id if appointment else None,
                appointment_week=_monday(appointment.date) if appointment else None,
                deadline_days=case.deadline_days,
                answers=dict(case.answers),
            )
    except SQLAlchemyError as exc:
        logger.warning("caso non salvato: %s", type(exc).__name__)
        return None
    return case_id


def _record_missing_procedure(rt: Runtime, result: TurnResult) -> None:
    """B1: registra un caso strutturato "procedura mancante" (nessun testo del cittadino)."""
    if not rt.db_enabled:
        return
    case = result.state.case
    try:
        with rt.db() as s:
            case_id: UUID = rt.repo.create_case(
                s,
                service_id=MISSING_PROCEDURE_SERVICE_ID,
                variant=None,
                category=case.category,
                language=result.language,
                office_id=None,
                appointment_week=None,
                deadline_days=None,
                answers={},
            )
            rt.repo.record_outcome(
                s,
                case_id,
                outcome="missing",
                cause=MISSING_PROCEDURE_CAUSE,
                missing_requirement_id=None,
                closed_in_time=None,
                rating=None,
            )
    except SQLAlchemyError as exc:
        logger.warning("procedura mancante non registrata: %s", type(exc).__name__)


def _record_outcome(
    rt: Runtime, chat: ChatSession, result: TurnResult, data: Mapping[str, object]
) -> None:
    """B8: salva l'esito raccontato in chat come i pulsanti della pagina esito."""
    outcome = data.get("outcome")
    case = result.state.case
    if chat.case_id is None or not rt.db_enabled or outcome not in OUTCOMES:
        return
    requirement_id = data.get("missing_requirement_id")
    if not isinstance(requirement_id, str) or case.service_id is None:
        requirement_id = None
    else:
        # Solo id presenti nella checklist del caso: mai un id inventato dal modello.
        try:
            checklist = rt.catalog().checklist(case.service_id, dict(case.answers))
            known = {item.id for item in checklist.items}
        except KnowledgeError:
            known = set()
        requirement_id = requirement_id if requirement_id in known else None
    try:
        with rt.db() as s:
            rt.repo.record_outcome(
                s,
                chat.case_id,
                outcome=outcome,
                cause=None,
                missing_requirement_id=requirement_id,
                closed_in_time=CLOSED_IN_TIME[str(outcome)],
                rating=None,
            )
    except SQLAlchemyError as exc:
        logger.warning("esito non salvato: %s", type(exc).__name__)


def _record_appointment_week(rt: Runtime, chat: ChatSession, result: TurnResult) -> None:
    """Salva sede e settimana dell'appuntamento sul caso (mai il giorno esatto in core)."""
    appointment = result.state.case.appointment
    if chat.case_id is None or appointment is None or not rt.db_enabled:
        return
    try:
        with rt.db() as s:
            rt.repo.update_case(
                s,
                chat.case_id,
                office_id=appointment.office_id,
                appointment_week=_monday(appointment.date),
            )
    except SQLAlchemyError as exc:
        logger.warning("appuntamento non salvato sul caso: %s", type(exc).__name__)


@router.post("/chat", response_class=HTMLResponse)
def chat(request: Request, message: Annotated[str, Form()] = "") -> Response:
    """Un turno di conversazione (HTMX): restituisce i nuovi messaggi da accodare."""
    rt = runtime(request)
    language = request_language(request)
    session_id, chat_session = rt.sessions.get(session_id_from_cookie(request))
    text = message.strip()[: rt.settings.max_message_chars]
    redacted = redact(text).text
    if not text:
        result = TurnResult(
            messages=[], language=chat_session.state.language, state=chat_session.state
        )
    else:
        result = _run_turn(rt, chat_session, redacted, language)
    chat_session.state = result.state
    show_contact = _handle_events(rt, chat_session, result)
    reply_lang = ui_language(result.language)
    labels = messages(reply_lang)
    rendered = [render_markdown(m, rt.source_link, labels) for m in result.messages]
    response = TEMPLATES.TemplateResponse(
        request,
        "partials/turn.html",
        context(
            reply_lang,
            user_text=redacted,
            replies=rendered,
            quick_replies=result.quick_replies,
            show_contact=show_contact,
            informativa=informativa(reply_lang) if show_contact else "",
        ),
    )
    response.set_cookie(
        COOKIE_NAME,
        signed_session_cookie(request, session_id),
        httponly=True,
        samesite="lax",
        max_age=rt.settings.session_ttl_s,
    )
    return response


@router.get("/case.ics")
def case_ics(request: Request) -> Response:
    """Promemoria per il calendario, senza dati personali, dall'appuntamento in sessione."""
    rt = runtime(request)
    chat_session = rt.sessions.peek(session_id_from_cookie(request))
    if chat_session is None or chat_session.state.case.appointment is None:
        return Response(status_code=404)
    appointment = chat_session.state.case.appointment
    start = datetime.combine(appointment.date, appointment.time, tzinfo=ROME)
    end = start + timedelta(minutes=ICS_DURATION_MIN)
    fmt = "%Y%m%dT%H%M%SZ"
    office = rt.catalog().office(appointment.office_id) if appointment.office_id else None
    body = TEMPLATES.get_template("case.ics").render(
        uid=f"{start.strftime(fmt)}@onevisit",
        stamp=datetime.now(ROME).astimezone(ZoneInfo("UTC")).strftime(fmt),
        start=start.astimezone(ZoneInfo("UTC")).strftime(fmt),
        end=end.astimezone(ZoneInfo("UTC")).strftime(fmt),
        summary=messages(chat_session.state.language)["ics_summary"],
        location=office.address if office else "",
    )
    return Response(
        content=body.replace("\n", "\r\n"),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="onevisit.ics"'},
    )
