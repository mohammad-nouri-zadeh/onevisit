"""Esecuzione degli strumenti chiamati da Claude (storie C3, B1, B3, B4).

Ogni strumento legge il catalogo, aggiorna ``CaseState`` solo con campi strutturati validati
contro il catalogo (id di servizio, id di opzione, numeri, date) ed emette ``AgentEvent``.
I risultati sono stringhe JSON con ``source_id``, citazione e data di verifica.
"""

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from typing import Any

from pydantic import ValidationError

from onevisit_agent.catalog_view import CatalogView, ChecklistView, ServiceView
from onevisit_agent.errors import ToolInputError
from onevisit_agent.models import AgentConfig, AgentEvent, AppointmentInfo, CaseState
from onevisit_agent.tool_schemas import (
    TOOL_INPUTS,
    BuildChecklistInput,
    GetOfficeInput,
    GetProcedureInput,
    IdentifyCaseInput,
    RecordAppointmentInput,
    RecordOutcomeInput,
    ReportMissingProcedureInput,
    RequestContactInput,
)

# Scadenza massima accettata, in giorni (oltre è quasi certamente un errore di calcolo).
MAX_DEADLINE_DAYS = 3650
# Formato degli id del catalogo: minuscole, cifre, trattini.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# Indizi di dati personali nel riepilogo generico di una procedura mancante.
_PII_HINT_RE = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.]+|[A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z]|\d{6,}"
)
# Tool che restituiscono fatti da mostrare al cittadino (la risposta deve citarli).
# Strumenti che restituiscono fatti del catalogo: dopo di loro la risposta deve citare (B3).
FACT_TOOLS = frozenset({"get_office", "build_checklist", "get_procedure"})


def _jsonable(value: object) -> Any:
    """Converte modelli, dataclass e date in strutture JSON."""
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return _jsonable(dump())
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(v) for v in value]
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    return value


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True)


class ToolRunner:
    """Esegue gli strumenti di un turno e raccoglie eventi e uso di fatti."""

    def __init__(self, *, catalog: CatalogView, config: AgentConfig, case: CaseState) -> None:
        self.catalog = catalog
        self.config = config
        self.case = case
        self.events: list[AgentEvent] = []
        self.used_facts = False

    def run(self, name: str, raw_input: dict[str, Any]) -> tuple[str, bool]:
        """Esegue lo strumento; restituisce (JSON, is_error). Mai eccezioni verso il ciclo."""
        model = TOOL_INPUTS.get(name)
        if model is None:
            return _dumps({"error": "unknown_tool"}), True
        try:
            args = model.model_validate(raw_input)
            result = getattr(self, f"_{name}")(args)
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
            return _dumps({"error": "invalid_input", "fields": fields}), True
        except ToolInputError as exc:
            return _dumps({"error": str(exc)}), True
        if name in FACT_TOOLS and result.get("has_facts"):
            self.used_facts = True
        return _dumps(result), False

    # --- servizio e caso -------------------------------------------------------------------

    def _service(self, service_id: str) -> ServiceView:
        service = self.catalog.service(service_id) if _ID_RE.match(service_id) else None
        if service is None:
            raise ToolInputError("unknown_service")
        return service

    def _valid_answers(self, service: ServiceView, answers: dict[str, str]) -> dict[str, str]:
        """Tiene solo coppie domanda/opzione presenti nel catalogo: niente testo libero."""
        options = {q.id: set(q.options) for q in service.deciding_questions}
        return {q: a for q, a in answers.items() if a in options.get(q, set())}

    def _identify_case(self, args: IdentifyCaseInput) -> dict[str, Any]:
        service = self._service(args.service_id)
        answers = {**self.case.answers, **self._valid_answers(service, args.answers)}
        first = next((q for q in service.deciding_questions if q.options), None)
        variant = args.variant if first and args.variant in first.options else None
        if variant is None and first is not None:
            variant = answers.get(first.id)
        if first is not None and variant is not None:
            answers[first.id] = variant
        if args.deadline_days is not None and 0 <= args.deadline_days <= MAX_DEADLINE_DAYS:
            self.case.deadline_days = args.deadline_days
        if self.case.service_id != service.id:
            answers = {
                k: v for k, v in answers.items() if k in {q.id for q in service.deciding_questions}
            }
        self.case.service_id = service.id
        self.case.variant = variant
        self.case.answers = answers
        self.case.category = args.category or self.case.category
        self.case.missing_procedure = False
        data: dict[str, str | int | bool | None] = {
            "service_id": service.id,
            "variant": variant,
            "deadline_days": self.case.deadline_days,
            "category": self.case.category,
        }
        self.events.append(AgentEvent(kind="case_identified", data=data))
        if args.confirmed and not self.case.confirmed:
            self.case.confirmed = True
            self.events.append(AgentEvent(kind="case_confirmed", data={"service_id": service.id}))
        still = [q.id for q in service.deciding_questions if q.id not in answers and q.options]
        return {"recorded": self.case.model_dump(exclude={"appointment"}), "still_to_ask": still}

    def _get_procedure(self, args: GetProcedureInput) -> dict[str, Any]:
        service = self._service(args.service_id)
        steps = sorted(service.steps, key=lambda s: s.order)
        sources = [self._source_info(sid) for sid in service.source_ids]
        return {
            "service_id": service.id,
            "title_it": service.title_it,
            "title_en": service.title_en,
            "deciding_questions": [
                {"id": q.id, "ask_it": q.ask_it, "ask_en": q.ask_en, "options": list(q.options)}
                for q in service.deciding_questions
            ],
            "already_answered": dict(self.case.answers),
            "steps": [
                {"order": s.order, "ente": s.ente, "text_it": s.text_it, "source_id": s.source_id}
                for s in steps
            ],
            "sources": [s for s in sources if s is not None],
            "not_verified_yet": list(service.unknowns_it),
            # Ordine degli enti e passi sono fatti: la risposta dovra' citarne la fonte (B3).
            "has_facts": bool(steps),
        }

    def _source_info(self, source_id: str) -> dict[str, Any] | None:
        source = self.catalog.source(source_id)
        if source is None:
            return None
        stale = self.catalog.is_stale(
            source_id, today=self.config.today, max_days=self.config.stale_after_days
        )
        return {
            "source_id": source.id,
            "title": source.title,
            "url": source.url,
            "verified_at": source.retrieved_at,
            "stale_warning": stale,
        }

    # --- sedi e checklist ------------------------------------------------------------------

    def _get_office(self, args: GetOfficeInput) -> dict[str, Any]:
        if args.office_id:
            office = self.catalog.office(args.office_id)
            offices = [office] if office is not None else []
        else:
            offices = list(self.catalog.offices(area=args.area, municipio=args.municipio))
        rows = []
        for office in offices:
            row = _jsonable(office)
            row = row if isinstance(row, dict) else {"id": office.id}
            row["source"] = self._source_info(office.source_id)
            rows.append(row)
        return {"offices": rows, "has_facts": bool(rows)}

    def _build_checklist(self, args: BuildChecklistInput) -> dict[str, Any]:
        service = self._service(args.service_id)
        answers = {**self.case.answers, **self._valid_answers(service, args.answers)}
        checklist = self.catalog.checklist(service.id, answers)
        return {
            "service_id": checklist.service_id,
            "items": [
                {
                    "id": i.id,
                    "text_it": i.text_it,
                    "text_en": i.text_en,
                    "source_id": i.source_id,
                    "quote": i.quote,
                    "verified_at": i.verified_at,
                    "lead_time_days": i.lead_time_days,
                }
                for i in checklist.items
            ],
            "still_to_ask": list(checklist.still_to_ask),
            "not_yet_verified": list(checklist.not_yet_verified),
            "has_facts": bool(checklist.items),
        }

    def _checklist(self) -> ChecklistView | None:
        if self.case.service_id is None:
            return None
        return self.catalog.checklist(self.case.service_id, self.case.answers)

    # --- appuntamento, contatti, esito -----------------------------------------------------

    def _record_appointment(self, args: RecordAppointmentInput) -> dict[str, Any]:
        try:
            day = date.fromisoformat(args.date)
            hour = time.fromisoformat(args.time)
        except ValueError as exc:
            raise ToolInputError("invalid_date_or_time") from exc
        days_left = (day - self.config.today).days
        if days_left < 0:
            raise ToolInputError("appointment_in_the_past")
        office_id = (
            args.office_id if args.office_id and self.catalog.office(args.office_id) else None
        )
        self.case.appointment = AppointmentInfo(date=day, time=hour, office_id=office_id)
        checklist = self._checklist()
        too_close = [
            {"requirement_id": i.id, "lead_time_days": i.lead_time_days, "source_id": i.source_id}
            for i in (checklist.items if checklist else [])
            if i.lead_time_days is not None and i.lead_time_days > days_left
        ]
        self.events.append(
            AgentEvent(
                kind="appointment_recorded",
                data={
                    "date": day.isoformat(),
                    "time": hour.isoformat("minutes"),
                    "office_id": office_id,
                    "days_left": days_left,
                },
            )
        )
        return {
            "recorded": True,
            "days_left": days_left,
            "office_id": office_id,
            "lead_time_warnings": too_close,
        }

    def _request_contact(self, _args: RequestContactInput) -> dict[str, Any]:
        if self.case.appointment is None:
            raise ToolInputError("no_appointment_recorded")
        self.events.append(AgentEvent(kind="contact_requested", data={}))
        return {"contact_form_shown": True}

    def _record_outcome(self, args: RecordOutcomeInput) -> dict[str, Any]:
        requirement_id = args.missing_requirement_id
        if requirement_id is not None and not _ID_RE.match(requirement_id):
            requirement_id = None
        self.events.append(
            AgentEvent(
                kind="outcome_recorded",
                data={"outcome": args.outcome, "missing_requirement_id": requirement_id},
            )
        )
        return {"recorded": True}

    def _report_missing_procedure(self, args: ReportMissingProcedureInput) -> dict[str, Any]:
        summary: str | None = args.summary_generalized.strip()
        if not summary or _PII_HINT_RE.search(summary):
            summary = None
        self.case.missing_procedure = True
        self.events.append(
            AgentEvent(kind="missing_procedure", data={"summary_generalized": summary})
        )
        return {"recorded": True, "official_site": self.config.official_fallback_url}
