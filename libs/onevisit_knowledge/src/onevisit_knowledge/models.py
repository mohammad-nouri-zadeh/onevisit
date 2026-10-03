"""Modelli Pydantic del catalogo e delle fonti (storie A1, A2, C4).

Contratto in docs/contracts.md, sezione 1.

Tutti i modelli sono immutabili (``frozen``): il catalogo caricato non cambia durante una
conversazione.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Id di fonte usato per le correzioni approvate nel pannello (B11).
APPROVED_CORRECTION_SOURCE_ID = "correzione-approvata"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Source(_Frozen):
    """Una riga di ``data/sources.csv``."""

    id: str
    title: str
    url: str = ""
    publisher: str = ""
    kind: str = ""
    snapshot: str = ""
    retrieved_at: date | None = None
    status: str = "todo"
    notes: str = ""


class DecidingQuestion(_Frozen):
    """Domanda che cambia la risposta (variante del servizio)."""

    id: str
    ask_it: str
    ask_en: str | None = None
    options: list[str] = Field(default_factory=list)
    kind: str | None = None


class Step(_Frozen):
    """Passaggio della procedura, anche presso altri enti."""

    order: int
    ente: str | None = None
    text_it: str
    text_en: str | None = None
    source_id: str
    quote: str | None = None
    verified_at: date | None = None
    status: str = "todo"


class Requirement(_Frozen):
    """Requisito come scritto nel file del servizio (anche non verificato)."""

    id: str
    text_it: str
    text_en: str | None = None
    when: dict[str, list[str]] = Field(default_factory=dict)
    source_id: str
    quote: str | None = None
    verified_at: date | None = None
    status: str = "todo"
    lead_time_days: int | None = None


class ApprovedCorrection(_Frozen):
    """Correzione approvata nel pannello (B11), sovrapposta al catalogo.

    Se ``requirement_id`` coincide con un requisito esistente lo sostituisce; altrimenti
    si aggiunge come requisito nuovo con id ``requirement_id`` o, se assente, ``id``.
    """

    id: str
    service_id: str
    requirement_id: str | None = None
    text_it: str
    text_en: str | None = None
    approved_at: datetime | date
    when: dict[str, list[str]] = Field(default_factory=dict)


class ChecklistItem(_Frozen):
    """Voce della checklist mostrata al cittadino."""

    id: str
    text_it: str
    text_en: str | None = None
    source_id: str
    quote: str | None = None
    verified_at: date | None = None
    lead_time_days: int | None = None
    origin: Literal["source", "approved_correction"] = "source"


class Checklist(_Frozen):
    """Checklist di un caso: voci, domande ancora da fare, requisiti non verificati, fonti."""

    service_id: str
    items: list[ChecklistItem]
    still_to_ask: list[str]
    not_yet_verified: list[str]
    sources: list[Source]


class ServiceSummary(_Frozen):
    """Riga dell'elenco dei servizi coperti."""

    id: str
    title_it: str
    title_en: str
    verified_requirements: int
    total_requirements: int


class Service(_Frozen):
    """Servizio con domande decisive e passaggi (solo verificati, salvo ``include_drafts``)."""

    id: str
    title_it: str
    title_en: str
    ente: str | None = None
    source_ids: list[str]
    deciding_questions: list[DecidingQuestion]
    steps: list[Step]
    unknowns_it: list[str]


class Office(_Frozen):
    """Sede anagrafica dal dataset ``ds549`` (``data/offices.json``)."""

    id: str
    municipio: int | None = None
    address: str = ""
    entrance_note: str | None = None
    phone: str | None = None
    hours_it: str | None = None
    notes_it: str | None = None
    appointment_only: bool | None = None
    booking_without_spid: bool | None = None
    nil_id: int | None = None
    nil_name: str | None = None
    lat: float | None = None
    lon: float | None = None
    source_id: str = "ds549"
    data_issues: list[str] = Field(default_factory=list)
    distance_km: float | None = None


class Ente(_Frozen):
    """Ente coinvolto in una procedura (``data/enti.json``)."""

    id: str
    name: str
    role_it: str = ""
    source_ids: list[str] = Field(default_factory=list)
    status: str = "todo"
