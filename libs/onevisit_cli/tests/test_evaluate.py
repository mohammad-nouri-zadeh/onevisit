"""Test del comando di valutazione (storia C13) con il client finto. Nessuna rete."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from onevisit_agent.testing import FakeClaudeClient, text_response, tool_response
from onevisit_cli import evaluate

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@dataclass(frozen=True)
class _Question:
    id: str
    ask_it: str
    ask_en: str | None
    options: tuple[str, ...]


@dataclass(frozen=True)
class _Step:
    order: int
    ente: str
    text_it: str
    source_id: str


@dataclass(frozen=True)
class _Service:
    id: str = "carta-identita"
    title_it: str = "Carta d'identità"
    title_en: str | None = "Identity card"
    source_ids: tuple[str, ...] = ("ds549",)
    deciding_questions: tuple[_Question, ...] = (
        _Question("motivo", "Motivo?", "Reason?", ("prima", "rinnovo", "smarrimento-furto")),
    )
    steps: tuple[_Step, ...] = ()
    unknowns_it: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Item:
    id: str = "su-appuntamento"
    text_it: str = "Solo su appuntamento"
    text_en: str | None = None
    source_id: str = "ds549"
    quote: str | None = "Tutti i servizi..."
    verified_at: date | None = date(2026, 10, 3)
    lead_time_days: int | None = None


@dataclass(frozen=True)
class _Checklist:
    service_id: str
    items: tuple[_Item, ...] = (_Item(),)
    still_to_ask: tuple[str, ...] = ()
    not_yet_verified: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Office:
    id: str
    source_id: str


@dataclass
class _Catalog:
    calls: list[str] = field(default_factory=list)

    def services(self) -> Sequence[_Service]:
        return [_Service()]

    def service(self, service_id: str) -> _Service | None:
        return _Service() if service_id == "carta-identita" else None

    def checklist(self, service_id: str, answers: Mapping[str, str]) -> _Checklist:
        return _Checklist(service_id=service_id)

    def source(self, source_id: str) -> None:
        return None

    def source_ids(self) -> frozenset[str]:
        return frozenset({"ds549"})

    def offices(
        self,
        *,
        area: str | None = None,
        municipio: int | None = None,
        lat: float | None = None,
        lon: float | None = None,
        limit: int = 3,
    ) -> Sequence[_Office]:
        return []

    def office(self, office_id: str) -> _Office | None:
        return None

    def is_stale(self, source_id: str, *, today: date, max_days: int) -> bool:
        return False


SCENARIO = evaluate.Scenario.model_validate(
    {
        "id": "cie-smarrimento-it",
        "messages": ["ho perso la carta d'identità"],
        "expect": {
            "service": "carta-identita",
            "variant": "smarrimento-furto",
            "language": "it",
            "requirements_include": ["su-appuntamento"],
            "forbidden_phrases": ["in regola"],
            "must_not_ask": ["codice fiscale"],
        },
    }
)


def test_missing_api_key_returns_2_with_clear_message(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    code = evaluate.run(
        data_dir=tmp_path,
        quick=True,
        report_path=tmp_path / "r.md",
        api_key="",
        model="claude-sonnet-5-5",
    )

    assert code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_passing_scenario_writes_report_and_returns_0(tmp_path: Path) -> None:
    client = FakeClaudeClient(
        script=[
            tool_response(
                ("identify_case", {"service_id": "carta-identita", "variant": "smarrimento-furto"})
            ),
            text_response("<lang>it</lang>Serve la prenotazione [fonte: ds549]. È per un adulto?"),
        ]
    )
    report = tmp_path / "eval-report.md"

    code = evaluate._run_scenarios(
        client=client,
        catalog=_Catalog(),
        scenarios=[SCENARIO],
        report_path=report,
        model="fake",
        today=date(2026, 10, 3),
    )

    assert code == 0
    assert "| `cie-smarrimento-it` | OK |" in report.read_text("utf-8")


def test_failing_scenario_returns_1_and_lists_failures(tmp_path: Path) -> None:
    client = FakeClaudeClient(
        script=[
            text_response("<lang>en</lang>What is your codice fiscale?"),
        ]
    )
    report = tmp_path / "eval-report.md"

    code = evaluate._run_scenarios(
        client=client,
        catalog=_Catalog(),
        scenarios=[SCENARIO],
        report_path=report,
        model="fake",
        today=date(2026, 10, 3),
    )

    text = report.read_text("utf-8")
    assert code == 1
    assert "FALLITO" in text
    assert "domanda vietata: codice fiscale" in text
    assert "language" in text


@pytest.mark.parametrize("quick, minimum", [(True, 5), (False, 15)])
def test_repository_scenarios_load(quick: bool, minimum: int) -> None:
    scenarios = evaluate.load_scenarios(DATA_DIR / "eval", quick=quick)

    assert len(scenarios) >= minimum
    if quick:
        assert len(scenarios) == 5
