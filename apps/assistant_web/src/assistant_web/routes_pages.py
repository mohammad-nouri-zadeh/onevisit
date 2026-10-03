"""Pagine personali con link firmati: checklist (B7), esito (B8), consensi (B9).

Verso il database vanno solo campi strutturati: il testo libero dell'esito passa da
``structure_feedback`` e non viene salvato.
"""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.exc import SQLAlchemyError

from assistant_web.i18n import ui_language
from assistant_web.runtime import Runtime
from assistant_web.web import TEMPLATES, context, runtime
from onevisit_channels import PURPOSE_CHECKLIST, PURPOSE_CONSENTS, PURPOSE_OUTCOME, LinkError
from onevisit_db.errors import DbError
from onevisit_knowledge import Checklist
from onevisit_privacy import structure_feedback

logger = logging.getLogger(__name__)
router = APIRouter()
SECONDS_PER_DAY = 86_400
# Valori ammessi per la valutazione dell'assistente.
RATING_MIN, RATING_MAX = 1, 5
OUTCOMES = ("ok", "missing", "other")


class _PageError(Exception):
    """Link non valido o dati non disponibili (nessun dettaglio personale nel messaggio)."""


def _verify(rt: Runtime, token: str, purpose: str) -> dict[str, str | None]:
    try:
        return rt.link_signer.verify(
            token, purpose, rt.settings.link_max_age_days * SECONDS_PER_DAY
        )
    except LinkError:
        raise _PageError("link") from None


def _error(request: Request, key: str = "error_link") -> Response:
    return TEMPLATES.TemplateResponse(
        request, "message.html", context("it", key=key), status_code=404
    )


def _load_case(rt: Runtime, case_id: UUID) -> tuple[str, Checklist]:
    """Lingua del caso e checklist del catalogo (solo requisiti verificati)."""
    if not rt.db_enabled:
        raise _PageError("db")
    with rt.db() as s:
        case = rt.repo.get_case(s, case_id)
        if case is None:
            raise _PageError("case")
        answers = rt.repo.case_answers(s, case_id)
    return ui_language(case.language), rt.catalog().checklist(case.service_id, answers)


def _items_view(rt: Runtime, checklist: Checklist, language: str) -> list[dict[str, Any]]:
    """Righe della checklist: nome ufficiale, spiegazione nella lingua, fonte, data."""
    rows: list[dict[str, Any]] = []
    for item in checklist.items:
        source = rt.source_link(item.source_id)
        rows.append(
            {
                "id": item.id,
                "official": item.text_it,
                "explained": item.text_en if language == "en" and item.text_en else item.text_it,
                "source_title": source.title if source else item.source_id,
                "source_url": source.url if source else "",
                "verified_at": item.verified_at.isoformat() if item.verified_at else None,
                "lead_time_days": item.lead_time_days,
            }
        )
    return rows


@router.api_route("/c/{token}", methods=["GET", "POST"], response_class=HTMLResponse)
async def checklist_page(request: Request, token: str) -> Response:
    """Checklist personale; con POST elenca cosa manca o la frase finale sulle fonti."""
    rt = runtime(request)
    form = await request.form() if request.method == "POST" else None
    try:
        data = _verify(rt, token, PURPOSE_CHECKLIST)
        language, checklist = _load_case(rt, UUID(str(data["case_id"])))
    except (_PageError, SQLAlchemyError, ValueError):
        return _error(request)
    items = _items_view(rt, checklist, language)
    have = {str(v) for v in form.getlist("have")} if form is not None else set()
    missing = [i for i in items if i["id"] not in have] if form is not None else None
    return TEMPLATES.TemplateResponse(
        request,
        "checklist.html",
        context(language, items=items, have=have, missing=missing, token=token),
    )


@router.get("/o/{token}", response_class=HTMLResponse)
def outcome_form(request: Request, token: str) -> Response:
    """Modulo dell'esito: tre pulsanti e domande facoltative."""
    rt = runtime(request)
    try:
        data = _verify(rt, token, PURPOSE_OUTCOME)
        language, checklist = _load_case(rt, UUID(str(data["case_id"])))
    except (_PageError, SQLAlchemyError, ValueError):
        return _error(request)
    items = _items_view(rt, checklist, language)
    return TEMPLATES.TemplateResponse(
        request, "outcome.html", context(language, items=items, token=token, done=False)
    )


def _rating(raw: str) -> int | None:
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if RATING_MIN <= value <= RATING_MAX else None


def _closed(raw: str) -> bool | None:
    return {"yes": True, "no": False}.get(raw)


@router.post("/o/{token}", response_class=HTMLResponse)
def outcome_submit(
    request: Request,
    token: str,
    outcome: Annotated[str, Form()] = "other",
    missing_id: Annotated[str, Form()] = "",
    missing_text: Annotated[str, Form()] = "",
    closed_in_time: Annotated[str, Form()] = "",
    rating: Annotated[str, Form()] = "",
    suggestion: Annotated[str, Form()] = "",
) -> Response:
    """Registra l'esito con soli campi strutturati; il testo libero non viene salvato."""
    rt = runtime(request)
    try:
        data = _verify(rt, token, PURPOSE_OUTCOME)
        case_id = UUID(str(data["case_id"]))
        language, checklist = _load_case(rt, case_id)
    except (_PageError, SQLAlchemyError, ValueError):
        return _error(request)
    known_ids = {item.id for item in checklist.items}
    requirement_id = missing_id if missing_id in known_ids else None
    cause: str | None = None
    client = rt.feedback_client()
    for text in (missing_text, suggestion):
        if text.strip():
            feedback = structure_feedback(text, client=client, model=rt.settings.model_fast)
            cause = cause or feedback.probable_cause
    try:
        with rt.db() as s:
            rt.repo.record_outcome(
                s,
                case_id,
                outcome=outcome if outcome in OUTCOMES else "other",
                cause=cause,
                missing_requirement_id=requirement_id,
                closed_in_time=_closed(closed_in_time),
                rating=_rating(rating),
            )
    except SQLAlchemyError as exc:
        logger.warning("esito non salvato: %s", type(exc).__name__)
        return _error(request, "error_db")
    return TEMPLATES.TemplateResponse(
        request, "message.html", context(language, key="outcome_thanks")
    )


@router.get("/consents/{token}", response_class=HTMLResponse)
def consents_form(request: Request, token: str) -> Response:
    """Pagina per revocare i consensi o cancellare il contatto."""
    rt = runtime(request)
    try:
        data = _verify(rt, token, PURPOSE_CONSENTS)
    except _PageError:
        return _error(request)
    if not data["contact_id"]:
        return _error(request)
    language = _contact_language(rt, UUID(str(data["contact_id"])))
    return TEMPLATES.TemplateResponse(request, "consents.html", context(language, token=token))


def _contact_language(rt: Runtime, contact_id: UUID) -> str:
    if not rt.db_enabled:
        return "it"
    try:
        with rt.db() as s:
            row = rt.repo.get_contact(s, contact_id)
    except SQLAlchemyError:
        return "it"
    return ui_language(row.language) if row is not None else "it"


@router.post("/consents/{token}", response_class=HTMLResponse)
def consents_submit(
    request: Request, token: str, action: Annotated[str, Form()] = "revoke"
) -> Response:
    """Revoca tutti i consensi o cancella il contatto; mostra la conferma."""
    rt = runtime(request)
    try:
        data = _verify(rt, token, PURPOSE_CONSENTS)
    except _PageError:
        return _error(request)
    if not data["contact_id"] or not rt.db_enabled:
        return _error(request)
    contact_id = UUID(str(data["contact_id"]))
    language = _contact_language(rt, contact_id)
    try:
        with rt.db() as s:
            if action == "delete":
                rt.repo.delete_contact(s, contact_id)
            else:
                rt.repo.revoke_consents(s, contact_id)
    except (SQLAlchemyError, DbError) as exc:
        logger.warning("consensi non aggiornati: %s", type(exc).__name__)
        return _error(request, "error_db")
    key = "consents_deleted" if action == "delete" else "consents_revoked"
    return TEMPLATES.TemplateResponse(request, "message.html", context(language, key=key))
