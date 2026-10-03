"""Modelli dei dati che attraversano il confine dell'agente (storie C3, B1, B2, B4).

``CaseState`` contiene solo campi strutturati (id di servizio, id di opzione, numeri, date):
il testo libero del cittadino non ci finisce mai (regola non negoziabile, C9).
"""

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["italiana", "ue", "extra-ue"]
EventKind = Literal[
    "case_identified",
    "case_confirmed",
    "appointment_recorded",
    "contact_requested",
    "outcome_recorded",
    "missing_procedure",
]
EventValue = str | int | bool | None


class AgentConfig(BaseModel):
    """Configurazione dell'agente, passata dall'app (le librerie non leggono l'ambiente)."""

    model_config = ConfigDict(frozen=True)

    model_conversation: str = "claude-sonnet-5-5"
    model_fast: str = "claude-haiku-4-5-20251001"
    official_fallback_url: str = "https://www.comune.milano.it/servizi"
    # Giorni oltre i quali una fonte è considerata da riverificare (B3).
    stale_after_days: int = 30
    today: date
    # Tetto di token per una risposta della conversazione: le risposte sono brevi.
    max_tokens: int = 4096
    # Numero massimo di giri strumento -> risposta in un turno, per evitare cicli.
    max_tool_rounds: int = 8


class Capabilities(BaseModel):
    """Cosa sa fare il canale da cui arriva il messaggio."""

    channel: Literal["web", "email", "sms"] = "web"
    buttons: bool = False
    max_chars: int | None = None
    browser_language: str | None = None


class AppointmentInfo(BaseModel):
    """Appuntamento indicato dal cittadino (B4): solo data, ora e sede."""

    date: date
    time: time
    office_id: str | None = None


class CaseState(BaseModel):
    """Stato strutturato del caso. Nessun testo libero."""

    service_id: str | None = None
    variant: str | None = None
    answers: dict[str, str] = Field(default_factory=dict)
    deadline_days: int | None = None
    category: Category | None = None
    confirmed: bool = False
    appointment: AppointmentInfo | None = None
    missing_procedure: bool = False


class SessionState(BaseModel):
    """Stato della sessione: lingua, storia per l'API (solo in memoria) e caso."""

    language: str = "it"
    history: list[dict[str, object]] = Field(default_factory=list)
    case: CaseState = Field(default_factory=CaseState)


class AgentEvent(BaseModel):
    """Evento strutturato emesso dagli strumenti, per l'applicazione (DB, lacune)."""

    kind: EventKind
    data: dict[str, EventValue] = Field(default_factory=dict)


class TurnResult(BaseModel):
    """Risultato di un turno di conversazione."""

    messages: list[str]
    quick_replies: list[str] = Field(default_factory=list)
    language: str
    state: SessionState
    blocked: bool = False
    events: list[AgentEvent] = Field(default_factory=list)
