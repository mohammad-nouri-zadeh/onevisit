"""Bozze di correzione in italiano, italiano facile e inglese (storia C10).

La bozza nomina la pagina e il testo da cambiare. Con un client Claude la scrive il
modello; senza client, o se la risposta non e' valida o contiene nomi propri, si usano
i modelli di testo in ``templates/``. La redazione rivede sempre la bozza (B11).
"""

import json
import logging
from importlib import resources
from string import Template

from pydantic import BaseModel, ConfigDict, ValidationError

from onevisit_analytics.claude import DEFAULT_MODEL, TextClient
from onevisit_analytics.errors import ClaudeOutputError, ProperNameError
from onevisit_analytics.names import ensure_no_proper_names

logger = logging.getLogger(__name__)

# Token massimi per le tre bozze in JSON.
DRAFT_MAX_TOKENS = 1200

DRAFT_SYSTEM = (
    "Scrivi la bozza di correzione di una pagina del Comune di Milano per la redazione. "
    "Indica la pagina e il testo da cambiare. Tre versioni: italiano, italiano facile "
    "(frasi brevi, parole comuni), inglese. Nessun nome di persona, nessun dato personale, "
    "nessuna promessa di esito. Rispondi solo con JSON: "
    '{"it": ..., "easy_it": ..., "en": ...}.'
)


class GapForDraft(BaseModel):
    """Dati aggregati di una lacuna, sufficienti a scrivere la bozza."""

    model_config = ConfigDict(frozen=True)

    service_id: str
    service_title: str
    source_id: str | None
    page_title: str | None
    cause: str
    requirement_id: str | None
    requirement_label: str | None
    case_count: int


class Draft(BaseModel):
    """Le tre versioni della bozza."""

    model_config = ConfigDict(frozen=True)

    it: str
    easy_it: str
    en: str
    by: str


def _template(name: str) -> Template:
    path = resources.files("onevisit_analytics").joinpath("templates", name)
    return Template(path.read_text(encoding="utf-8").strip())


def draft_correction(
    gap: GapForDraft, *, client: TextClient | None = None, model: str = DEFAULT_MODEL
) -> Draft:
    """Scrive la bozza; ripiega sui modelli di testo se Claude non e' disponibile."""
    if client is not None:
        try:
            return _draft_with_claude(gap, client=client, model=model)
        except (ClaudeOutputError, ProperNameError):
            logger.warning("bozza di Claude scartata: uso i modelli di testo")
    return draft_by_template(gap)


def draft_by_template(gap: GapForDraft) -> Draft:
    """Bozza deterministica dai modelli di testo."""
    values = {
        "page": gap.page_title or gap.source_id or "pagina del servizio",
        "service": gap.service_title,
        "requirement": gap.requirement_label or gap.requirement_id or "requisito da definire",
        "cause": gap.cause,
    }
    return Draft(
        it=_template("draft_it.txt").substitute(values),
        easy_it=_template("draft_easy_it.txt").substitute(values),
        en=_template("draft_en.txt").substitute(values),
        by="regola",
    )


def _draft_with_claude(gap: GapForDraft, *, client: TextClient, model: str) -> Draft:
    raw = client.complete(
        model=model,
        system=DRAFT_SYSTEM,
        prompt=json.dumps(gap.model_dump(mode="json"), ensure_ascii=False),
        max_tokens=DRAFT_MAX_TOKENS,
    )
    try:
        data = json.loads(raw)
        draft = Draft(it=data["it"], easy_it=data["easy_it"], en=data["en"], by="claude")
    except (ValueError, KeyError, TypeError, ValidationError) as exc:
        raise ClaudeOutputError("bozza non valida") from exc
    ensure_no_proper_names([draft.it, draft.easy_it, draft.en])
    return draft
