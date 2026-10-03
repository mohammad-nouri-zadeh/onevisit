"""Classificazione di un esito negativo in una delle sei cause (storia C10).

Ingresso: solo campi strutturati del caso, mai testo libero del cittadino.
Con un client Claude si chiede la causa in JSON; se la risposta non e' valida, o se
manca il client, decide la regola deterministica.
"""

import json
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from onevisit_analytics.causes import Cause
from onevisit_analytics.claude import DEFAULT_MODEL, TextClient
from onevisit_analytics.errors import ClaudeOutputError

logger = logging.getLogger(__name__)

# Token massimi per la risposta JSON della classificazione.
CLASSIFY_MAX_TOKENS = 300
# Confidenza della regola quando la causa e' gia' dichiarata o la regola e' certa.
RULE_CONFIDENCE_HIGH = 0.9
# Confidenza della regola quando deduce la causa da indizi parziali.
RULE_CONFIDENCE_LOW = 0.5

CLASSIFY_SYSTEM = (
    "Classifichi l'esito negativo di un appuntamento all'anagrafe in una di sei cause: "
    "pagina-incompleta, procedura-non-aggiornata, procedura-mancante, "
    "ente-o-ufficio-sbagliato, pagina-chiara-non-seguita, richiesta-non-prevista. "
    "Ragioni solo per procedura e sede, mai per persona: non scrivere nomi propri. "
    'Rispondi solo con JSON: {"cause": ..., "motivation": ..., "confidence": 0..1}.'
)


class OutcomeInput(BaseModel):
    """Campi strutturati di un esito, senza testo libero."""

    model_config = ConfigDict(frozen=True)

    service_id: str
    outcome: Literal["ok", "missing", "other"]
    declared_cause: Cause | None = None
    missing_requirement_id: str | None = None
    requirement_on_page: bool | None = None
    wrong_office: bool = False
    missing_procedure: bool = False


class Classification(BaseModel):
    """Causa con motivazione breve e livello di confidenza."""

    model_config = ConfigDict(frozen=True)

    cause: Cause
    motivation: str = Field(max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    by: Literal["claude", "regola"]


def classify_outcome(
    outcome: OutcomeInput, *, client: TextClient | None = None, model: str = DEFAULT_MODEL
) -> Classification | None:
    """Assegna una causa a un esito negativo; ``None`` per un esito positivo."""
    if outcome.outcome == "ok":
        return None
    if client is not None:
        try:
            return _classify_with_claude(outcome, client=client, model=model)
        except ClaudeOutputError:
            logger.warning("classificazione di Claude non valida: uso la regola")
    return classify_by_rule(outcome)


def classify_by_rule(outcome: OutcomeInput) -> Classification:
    """Regola deterministica, usata nei test e senza chiave API."""
    if outcome.declared_cause is not None:
        return _rule(outcome.declared_cause, "causa indicata dall'esito", RULE_CONFIDENCE_HIGH)
    if outcome.missing_procedure:
        return _rule(Cause.PROCEDURA_MANCANTE, "procedura non descritta", RULE_CONFIDENCE_HIGH)
    if outcome.wrong_office:
        return _rule(Cause.ENTE_O_UFFICIO_SBAGLIATO, "sede o ente sbagliato", RULE_CONFIDENCE_HIGH)
    if outcome.missing_requirement_id is None:
        return _rule(Cause.RICHIESTA_NON_PREVISTA, "requisito non previsto", RULE_CONFIDENCE_LOW)
    if outcome.requirement_on_page:
        return _rule(Cause.PAGINA_CHIARA_NON_SEGUITA, "requisito presente", RULE_CONFIDENCE_LOW)
    return _rule(Cause.PAGINA_INCOMPLETA, "requisito non sulla pagina", RULE_CONFIDENCE_LOW)


def _rule(cause: Cause, motivation: str, confidence: float) -> Classification:
    return Classification(cause=cause, motivation=motivation, confidence=confidence, by="regola")


def _classify_with_claude(
    outcome: OutcomeInput, *, client: TextClient, model: str
) -> Classification:
    prompt = json.dumps(outcome.model_dump(mode="json"), ensure_ascii=False)
    raw = client.complete(
        model=model, system=CLASSIFY_SYSTEM, prompt=prompt, max_tokens=CLASSIFY_MAX_TOKENS
    )
    try:
        data = json.loads(raw)
        return Classification(
            cause=Cause(data["cause"]),
            motivation=str(data["motivation"]),
            confidence=float(data["confidence"]),
            by="claude",
        )
    except (ValueError, KeyError, TypeError, ValidationError) as exc:
        raise ClaudeOutputError("risposta di classificazione non valida") from exc
