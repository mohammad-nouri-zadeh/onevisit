"""Comando ``onevisit eval``: scenari di valutazione dell'agente con la vera API (storia C13).

Ogni scenario in ``data/eval/*.yaml`` passa dall'``Agent`` reale; si verificano servizio,
variante, lingua, requisiti, citazioni, parole vietate, domande vietate e assenza di dati
personali nello stato del caso. Il report è in Markdown; codice d'uscita 1 se uno scenario
fallisce, 2 se manca la chiave API. ``_run_scenarios`` accetta un client iniettabile per i test.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from onevisit_agent import (
    Agent,
    AgentConfig,
    AnthropicClaudeClient,
    Capabilities,
    CatalogView,
    ClaudeClient,
    SessionState,
)

# Indizi di dati personali che non devono mai comparire nello stato del caso.
_PII_RE = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.]+|[A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z]|\+?\d[\d ]{7,}"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?\n])\s+")


class Expect(BaseModel):
    """Attese di uno scenario."""

    model_config = ConfigDict(extra="forbid")

    service: str | None = None
    variant: str | None = None
    language: str | None = None
    requirements_include: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    must_not_ask: list[str] = Field(default_factory=list)
    missing_procedure: bool = False
    deadline_set: bool = False
    citations: bool | None = None


class Scenario(BaseModel):
    """Uno scenario di valutazione."""

    model_config = ConfigDict(extra="forbid")

    id: str
    quick: bool = False
    messages: list[str]
    expect: Expect


@dataclass
class ScenarioResult:
    """Esito di uno scenario: elenco dei controlli falliti."""

    scenario_id: str
    failures: list[str] = field(default_factory=list)
    blocked_turns: int = 0

    @property
    def passed(self) -> bool:
        return not self.failures


def load_scenarios(eval_dir: Path, *, quick: bool) -> list[Scenario]:
    """Legge gli scenari, ordinati per nome di file; con ``quick`` solo quelli veloci."""
    scenarios = [
        Scenario.model_validate(yaml.safe_load(path.read_text("utf-8")))
        for path in sorted(eval_dir.glob("*.yaml"))
    ]
    return [s for s in scenarios if s.quick or not quick]


def _asked(replies: list[str], phrase: str) -> bool:
    """Vero se una frase interrogativa delle risposte contiene ``phrase``."""
    needle = phrase.casefold()
    for reply in replies:
        for sentence in _SENTENCE_SPLIT_RE.split(reply):
            if sentence.strip().endswith("?") and needle in sentence.casefold():
                return True
    return False


def _check(
    scenario: Scenario,
    replies: list[str],
    languages: list[str],
    state: SessionState,
    catalog: CatalogView,
) -> list[str]:
    """Confronta lo stato finale e le risposte con le attese."""
    exp, case, failures = scenario.expect, state.case, []
    if case.service_id != exp.service:
        failures.append(f"service: atteso {exp.service}, ottenuto {case.service_id}")
    if exp.variant is not None and case.variant != exp.variant:
        failures.append(f"variant: attesa {exp.variant}, ottenuta {case.variant}")
    if exp.language and (not languages or languages[-1] != exp.language):
        failures.append(f"language: attesa {exp.language}, ottenuta {languages[-1:]}")
    if exp.missing_procedure and not case.missing_procedure:
        failures.append("missing_procedure non registrata")
    if exp.deadline_set and case.deadline_days is None:
        failures.append("scadenza non salvata in giorni")
    if exp.requirements_include and case.service_id:
        ids = {i.id for i in catalog.checklist(case.service_id, case.answers).items}
        failures.extend(
            f"requisito mancante: {r}" for r in exp.requirements_include if r not in ids
        )
    text = "\n".join(replies).casefold()
    failures.extend(f"frase vietata: {p}" for p in exp.forbidden_phrases if p.casefold() in text)
    failures.extend(f"domanda vietata: {p}" for p in exp.must_not_ask if _asked(replies, p))
    wants_citations = exp.citations if exp.citations is not None else exp.service is not None
    if wants_citations and "[fonte:" not in text:
        failures.append("nessuna citazione [fonte: ...]")
    if _PII_RE.search(case.model_dump_json()):
        failures.append("dati personali nello stato del caso")
    return failures


def _run_one(agent: Agent, scenario: Scenario, catalog: CatalogView) -> ScenarioResult:
    state, replies, languages = SessionState(), [], []
    result = ScenarioResult(scenario_id=scenario.id)
    caps = Capabilities(channel="web", buttons=True)
    for message in scenario.messages:
        turn = agent.run_turn(state, message, caps)
        state = turn.state
        replies.extend(turn.messages)
        languages.append(turn.language)
        result.blocked_turns += int(turn.blocked)
    result.failures = _check(scenario, replies, languages, state, catalog)
    return result


def write_report(results: list[ScenarioResult], report_path: Path, *, model: str) -> None:
    """Scrive il report Markdown (nessun testo delle conversazioni, solo esiti)."""
    passed = sum(r.passed for r in results)
    lines = [
        "# Valutazione dell'agente (C13)",
        "",
        f"Modello: `{model}` · Data: {date.today().isoformat()} · "
        f"Superati: **{passed}/{len(results)}**",
        "",
        "| Scenario | Esito | Turni bloccati | Controlli falliti |",
        "|---|---|---|---|",
    ]
    for r in results:
        outcome = "OK" if r.passed else "FALLITO"
        lines.append(
            f"| `{r.scenario_id}` | {outcome} | {r.blocked_turns} | "
            f"{'; '.join(r.failures) or '-'} |"
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_scenarios(
    *,
    client: ClaudeClient,
    catalog: CatalogView,
    scenarios: list[Scenario],
    report_path: Path,
    model: str,
    today: date,
) -> int:
    """Esegue gli scenari con il client dato (iniettabile nei test) e scrive il report."""
    config = AgentConfig(model_conversation=model, today=today)
    agent = Agent(client=client, catalog=catalog, config=config)
    results = [_run_one(agent, s, catalog) for s in scenarios]
    write_report(results, report_path, model=model)
    for r in results:
        print(f"{'OK     ' if r.passed else 'FALLITO'} {r.scenario_id}")
    print(f"Report: {report_path}")
    return 0 if all(r.passed for r in results) else 1


def _load_catalog(data_dir: Path) -> CatalogView:
    """Carica il catalogo reale (onevisit_knowledge, docs/contracts.md sezione 1)."""
    from onevisit_knowledge import load_catalog

    return load_catalog(data_dir)


def run(*, data_dir: Path, quick: bool, report_path: Path, api_key: str, model: str) -> int:
    """Punto d'ingresso del comando: 2 senza chiave API, 1 se uno scenario fallisce."""
    if not api_key:
        print(
            "ANTHROPIC_API_KEY non impostata: la valutazione chiama la vera API di Claude. "
            "Imposta la chiave in .env e riprova."
        )
        return 2
    scenarios = load_scenarios(data_dir / "eval", quick=quick)
    if not scenarios:
        print(f"Nessuno scenario in {data_dir / 'eval'}")
        return 1
    return _run_scenarios(
        client=AnthropicClaudeClient(api_key),
        catalog=_load_catalog(data_dir),
        scenarios=scenarios,
        report_path=report_path,
        model=model,
        today=date.today(),
    )
