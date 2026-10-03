"""Catalogo finto e fixture per i test dell'agente (storia C3). Dati sintetici."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

import pytest

from onevisit_agent import Agent, AgentConfig
from onevisit_agent.testing import FakeClaudeClient

TODAY = date(2026, 10, 3)


@dataclass(frozen=True)
class FakeSource:
    id: str
    title: str
    url: str
    retrieved_at: date | None


@dataclass(frozen=True)
class FakeQuestion:
    id: str
    ask_it: str
    ask_en: str | None
    options: tuple[str, ...]


@dataclass(frozen=True)
class FakeStep:
    order: int
    ente: str
    text_it: str
    source_id: str


@dataclass(frozen=True)
class FakeSummary:
    id: str
    title_it: str
    title_en: str | None


@dataclass(frozen=True)
class FakeService:
    id: str
    title_it: str
    title_en: str | None
    source_ids: tuple[str, ...]
    deciding_questions: tuple[FakeQuestion, ...]
    steps: tuple[FakeStep, ...]
    unknowns_it: tuple[str, ...] = ()


@dataclass(frozen=True)
class FakeItem:
    id: str
    text_it: str
    text_en: str | None
    source_id: str
    quote: str | None
    verified_at: date | None
    lead_time_days: int | None = None


@dataclass(frozen=True)
class FakeChecklist:
    service_id: str
    items: tuple[FakeItem, ...]
    still_to_ask: tuple[str, ...] = ()
    not_yet_verified: tuple[str, ...] = ()


@dataclass(frozen=True)
class FakeOffice:
    id: str
    source_id: str
    address: str
    hours_it: str
    municipio: int


SERVICE = FakeService(
    id="carta-identita",
    title_it="Carta d'identità elettronica",
    title_en="Electronic identity card",
    source_ids=("cie", "ds549"),
    deciding_questions=(
        FakeQuestion("motivo", "Motivo?", "Reason?", ("prima", "rinnovo", "smarrimento-furto")),
        FakeQuestion("eta", "Età?", "Age?", ("adulto", "minore")),
    ),
    steps=(FakeStep(1, "comune-milano", "Prenota e vai allo sportello", "ds549"),),
)
ITEMS = (
    FakeItem(
        "su-appuntamento",
        "Solo su appuntamento",
        "By appointment",
        "ds549",
        "Tutti i servizi...",
        TODAY,
    ),
    FakeItem(
        "traduzione",
        "Traduzione giurata",
        "Sworn translation",
        "cie",
        "Traduzione...",
        TODAY,
        lead_time_days=20,
    ),
)


@dataclass
class FakeCatalog:
    """Catalogo minimo che soddisfa ``CatalogView``; registra le chiamate."""

    calls: list[tuple[str, object]] = field(default_factory=list)
    stale: bool = False

    def services(self) -> Sequence[FakeSummary]:
        return [FakeSummary(SERVICE.id, SERVICE.title_it, SERVICE.title_en)]

    def service(self, service_id: str) -> FakeService | None:
        self.calls.append(("service", service_id))
        return SERVICE if service_id == SERVICE.id else None

    def checklist(self, service_id: str, answers: Mapping[str, str]) -> FakeChecklist:
        self.calls.append(("checklist", (service_id, dict(answers))))
        return FakeChecklist(service_id=service_id, items=ITEMS, not_yet_verified=("costo",))

    def source(self, source_id: str) -> FakeSource | None:
        if source_id not in self.source_ids():
            return None
        return FakeSource(
            source_id, f"Pagina {source_id}", "https://www.comune.milano.it/x", date(2026, 8, 1)
        )

    def source_ids(self) -> frozenset[str]:
        return frozenset({"cie", "ds549"})

    def offices(
        self,
        *,
        area: str | None = None,
        municipio: int | None = None,
        lat: float | None = None,
        lon: float | None = None,
        limit: int = 3,
    ) -> Sequence[FakeOffice]:
        self.calls.append(("offices", (area, municipio)))
        return [FakeOffice("ds549-01", "ds549", "via Larga 12", "8:30-15:30", 1)]

    def office(self, office_id: str) -> FakeOffice | None:
        self.calls.append(("office", office_id))
        return (
            FakeOffice("ds549-01", "ds549", "via Larga 12", "8:30-15:30", 1)
            if (office_id == "ds549-01")
            else None
        )

    def is_stale(self, source_id: str, *, today: date, max_days: int) -> bool:
        self.calls.append(("is_stale", (source_id, today, max_days)))
        return self.stale


@pytest.fixture
def catalog() -> FakeCatalog:
    return FakeCatalog()


@pytest.fixture
def config() -> AgentConfig:
    return AgentConfig(today=TODAY, official_fallback_url="https://www.comune.milano.it/servizi")


@pytest.fixture
def make_agent(catalog: FakeCatalog, config: AgentConfig):  # type: ignore[no-untyped-def]
    def _make(client: FakeClaudeClient) -> Agent:
        return Agent(client=client, catalog=catalog, config=config)

    return _make
