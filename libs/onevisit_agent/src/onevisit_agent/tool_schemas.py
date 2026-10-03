"""Modelli Pydantic degli argomenti degli strumenti e definizioni per l'API (storia C3).

Lo schema JSON passato a Claude si genera da questi modelli. Nessuno strumento prenota:
``record_appointment`` registra solo un appuntamento già preso dal cittadino.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from onevisit_agent.models import Category


class _ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdentifyCaseInput(_ToolInput):
    """Servizio, variante e risposte già note (solo id di opzione, mai testo libero)."""

    service_id: str = Field(description="Id del servizio dall'indice del catalogo.")
    variant: str | None = Field(
        default=None, description="Id dell'opzione della prima domanda decisiva, se nota."
    )
    answers: dict[str, str] = Field(
        default_factory=dict, description="question_id -> option id, solo risposte già date."
    )
    deadline_days: int | None = Field(
        default=None, description="Giorni entro cui serve il documento, se c'è una scadenza."
    )
    category: Category | None = Field(default=None, description="Cittadinanza della persona.")
    language: str | None = Field(default=None, description="Lingua del cittadino, ISO 639-1.")
    confirmed: bool = Field(
        default=False, description="True solo dopo che il cittadino ha confermato il riepilogo."
    )


class GetProcedureInput(_ToolInput):
    """Procedura di un servizio: domande decisive, passaggi verificati, fonti."""

    service_id: str


class GetOfficeInput(_ToolInput):
    """Sedi anagrafiche per zona, municipio o id."""

    area: str | None = Field(default=None, description="Quartiere o zona di Milano.")
    municipio: int | None = Field(default=None, ge=1, le=9)
    office_id: str | None = None


class BuildChecklistInput(_ToolInput):
    """Checklist dei requisiti verificati per le risposte date."""

    service_id: str
    answers: dict[str, str] = Field(default_factory=dict)


class RecordAppointmentInput(_ToolInput):
    """Appuntamento già preso dal cittadino sul sistema ufficiale."""

    date: str = Field(description="Data dell'appuntamento, formato YYYY-MM-DD.")
    time: str = Field(description="Ora dell'appuntamento, formato HH:MM.")
    office_id: str | None = Field(default=None, description="Id della sede da get_office.")


class RequestContactInput(_ToolInput):
    """Chiede all'applicazione di mostrare il modulo per i contatti."""


class RecordOutcomeInput(_ToolInput):
    """Esito della visita raccontato dal cittadino."""

    outcome: Literal["ok", "missing", "other"]
    missing_requirement_id: str | None = None


class ReportMissingProcedureInput(_ToolInput):
    """Servizio non presente nel catalogo, descritto in modo generico."""

    summary_generalized: str = Field(
        description="Descrizione generica del servizio richiesto, senza alcun dato personale.",
        max_length=200,
    )


TOOL_INPUTS: dict[str, type[_ToolInput]] = {
    "identify_case": IdentifyCaseInput,
    "get_procedure": GetProcedureInput,
    "get_office": GetOfficeInput,
    "build_checklist": BuildChecklistInput,
    "record_appointment": RecordAppointmentInput,
    "request_contact": RequestContactInput,
    "record_outcome": RecordOutcomeInput,
    "report_missing_procedure": ReportMissingProcedureInput,
}

_DESCRIPTIONS: dict[str, str] = {
    "identify_case": (
        "Record the structured case: service, variant, answers (option ids only), deadline in "
        "days, citizen category, language. Call it as soon as the service is clear and again "
        "when answers change; set confirmed=true only after the citizen confirms the summary."
    ),
    "get_procedure": (
        "Get a service's deciding questions, verified steps (enti in order, with why), sources "
        "with official URLs and what is not yet verified. Only source of procedure facts."
    ),
    "get_office": (
        "Get City registry offices (address, hours, booking notes, data issues, source, "
        "verification date, stale warning) by area, municipio (1-9) or office_id."
    ),
    "build_checklist": (
        "Build the checklist of verified requirements for the answers given, with source_id, "
        "quote and verification date. Lists what is still to ask and what is not verified."
    ),
    "record_appointment": (
        "Record an appointment the citizen ALREADY booked on the official system (date, time, "
        "office). Never books. Returns warnings when a requirement needs more lead time."
    ),
    "request_contact": (
        "Ask the app to show the contact-preferences form. Only after an appointment is recorded."
    ),
    "record_outcome": (
        "Record how the visit went: ok, missing (with the requirement id if known) or other."
    ),
    "report_missing_procedure": (
        "Report that the requested service is not in the catalog, with a generic summary and "
        "no personal data. Then point the citizen to the City website."
    ),
}


def tool_definitions() -> list[dict[str, Any]]:
    """Definizioni degli strumenti per l'API, in ordine fisso (il prompt caching lo richiede)."""
    tools: list[dict[str, Any]] = []
    for name, model in TOOL_INPUTS.items():
        schema = model.model_json_schema()
        schema.pop("title", None)
        schema.pop("description", None)
        tools.append({"name": name, "description": _DESCRIPTIONS[name], "input_schema": schema})
    tools[-1]["cache_control"] = {"type": "ephemeral"}
    return tools
