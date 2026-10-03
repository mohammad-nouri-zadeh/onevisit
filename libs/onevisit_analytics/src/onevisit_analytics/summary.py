"""Sintesi settimanale in linguaggio semplice (storia B13).

Usa solo numeri presi dalle viste aggregate (gia' filtrate con la soglia k): mai casi
singoli, mai persone o dipendenti. Massimo 200 parole: cosa e' migliorato, cosa e'
peggiorato e tre interventi consigliati. Senza client Claude usa il modello di testo.
"""

import json
import logging
from importlib import resources
from string import Template

from pydantic import BaseModel, ConfigDict

from onevisit_analytics.claude import DEFAULT_MODEL, TextClient
from onevisit_analytics.errors import ClaudeOutputError, ProperNameError
from onevisit_analytics.names import ensure_no_proper_names

logger = logging.getLogger(__name__)

# Limite di parole della sintesi (B13).
SUMMARY_MAX_WORDS = 200
# Token massimi per la sintesi.
SUMMARY_MAX_TOKENS = 600
# Numero di interventi consigliati.
RECOMMENDATIONS = 3

SUMMARY_SYSTEM = (
    "Scrivi in italiano semplice la sintesi settimanale del pannello OneVisit per la "
    "direzione dei servizi anagrafici del Comune di Milano. Massimo 200 parole. Usa solo "
    "i numeri forniti, che sono aggregati. Di' cosa e' migliorato, cosa e' peggiorato e "
    "proponi tre interventi, rimandando alle tabelle del pannello. Nessun nome di persona."
)


class ServiceTrend(BaseModel):
    """Tasso di chiusura al primo appuntamento: ultima settimana e precedente."""

    model_config = ConfigDict(frozen=True)

    service_id: str
    rate_now: float | None
    rate_before: float | None


class CauseCount(BaseModel):
    """Lacune aperte per causa (``cases`` nullo sotto soglia)."""

    model_config = ConfigDict(frozen=True)

    cause: str
    open_gaps: int
    cases: int | None


class Effect(BaseModel):
    """Effetto prima e dopo di una correzione (nullo sotto soglia)."""

    model_config = ConfigDict(frozen=True)

    service_id: str
    requirement_id: str | None
    rate_before: float | None
    rate_after: float | None


class WeeklyData(BaseModel):
    """Ingresso della sintesi: solo aggregati."""

    model_config = ConfigDict(frozen=True)

    k_threshold: int
    trends: list[ServiceTrend]
    causes: list[CauseCount]
    effects: list[Effect]


def weekly_summary(
    data: WeeklyData, *, client: TextClient | None = None, model: str = DEFAULT_MODEL
) -> str:
    """Restituisce la sintesi (al massimo 200 parole)."""
    if client is not None:
        try:
            text = client.complete(
                model=model,
                system=SUMMARY_SYSTEM,
                prompt=json.dumps(data.model_dump(mode="json"), ensure_ascii=False),
                max_tokens=SUMMARY_MAX_TOKENS,
            ).strip()
            ensure_no_proper_names([text])
            if text:
                return _truncate(text)
        except (ProperNameError, ClaudeOutputError) as exc:
            logger.warning("sintesi di Claude scartata (%s): uso il modello", type(exc).__name__)
    return _truncate(summary_by_template(data))


def _pct(value: float | None) -> str:
    return "dati insufficienti" if value is None else f"{value * 100:.0f}%"


def summary_by_template(data: WeeklyData) -> str:
    """Sintesi deterministica dal modello di testo."""
    rates = "; ".join(f"{t.service_id} {_pct(t.rate_now)}" for t in data.trends) or "nessun dato"
    improved = _changes(data.trends, better=True)
    worsened = _changes(data.trends, better=False)
    gaps = "; ".join(
        f"{c.cause} {c.open_gaps} ({c.cases if c.cases is not None else 'dati insufficienti'} casi)"
        for c in data.causes
        if c.open_gaps
    )
    effects = "; ".join(
        f"{e.service_id} da {_pct(e.rate_before)} a {_pct(e.rate_after)}" for e in data.effects
    )
    recs = _recommendations(data)
    template = resources.files("onevisit_analytics").joinpath("templates", "summary_it.txt")
    return Template(template.read_text(encoding="utf-8").strip()).substitute(
        k=data.k_threshold,
        rates=rates,
        improved=improved or "nessuna variazione rilevante",
        worsened=worsened or "nessuna variazione rilevante",
        gaps=gaps or "nessuna",
        effects=effects or "nessuna correzione misurabile",
        rec1=recs[0],
        rec2=recs[1],
        rec3=recs[2],
    )


def _changes(trends: list[ServiceTrend], *, better: bool) -> str:
    items = []
    for t in trends:
        if t.rate_now is None or t.rate_before is None or t.rate_now == t.rate_before:
            continue
        if (t.rate_now > t.rate_before) == better:
            items.append(f"{t.service_id} da {_pct(t.rate_before)} a {_pct(t.rate_now)}")
    return "; ".join(items)


def _recommendations(data: WeeklyData) -> list[str]:
    ranked = sorted(data.causes, key=lambda c: (c.cases or 0, c.open_gaps), reverse=True)
    recs = [f"rivedere le lacune {c.cause} nella pagina Lacune" for c in ranked if c.open_gaps]
    recs += [
        "verificare con gli uffici le segnalazioni sopra soglia",
        "controllare nella pagina Interventi l'effetto delle correzioni approvate",
        "aggiornare le pagine non verificate di recente",
    ]
    return recs[:RECOMMENDATIONS]


def _truncate(text: str) -> str:
    words = text.split()
    return text if len(words) <= SUMMARY_MAX_WORDS else " ".join(words[:SUMMARY_MAX_WORDS])
