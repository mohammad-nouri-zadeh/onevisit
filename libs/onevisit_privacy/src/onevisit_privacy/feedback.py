"""Secondo passaggio della pipeline privacy: testo libero -> campi strutturati (storia C9).

Il testo del cittadino passa sempre prima da :func:`redact`; solo il testo ripulito
puo' arrivare al modello (Haiku). Si salva soltanto :class:`StructuredFeedback`,
mai il testo originale. I campi restituiti sono controllati di nuovo: se contengono
dati personali o parole che sembrano nomi propri presenti nel testo, vengono scartati.
"""

import json
import re
from typing import Literal, Protocol, get_args

from pydantic import BaseModel, ConfigDict, ValidationError

from onevisit_privacy.errors import ClaudeUnavailableError
from onevisit_privacy.redact import contains_pii, redact

Cause = Literal[
    "pagina-incompleta",
    "procedura-non-aggiornata",
    "procedura-mancante",
    "ente-o-ufficio-sbagliato",
    "pagina-chiara-non-seguita",
    "richiesta-non-prevista",
]
CAUSES: tuple[Cause, ...] = get_args(Cause)

Tone = Literal["neutro", "frustrato", "positivo"]

# Modello veloce previsto dal backlog per questo passaggio.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
# Risposta breve: un oggetto JSON con quattro campi.
MAX_TOKENS = 400
# Lunghezza massima di un campo generalizzato salvato.
MAX_FIELD_CHARS = 300

# Parole con iniziale maiuscola che non sono nomi di persona (istituzioni, documenti).
_ALLOWED_CAPITALISED = frozenset(
    {
        "comune",
        "milano",
        "anagrafe",
        "questura",
        "prefettura",
        "italia",
        "italy",
        "ue",
        "eu",
        "spid",
        "cie",
        "inps",
        "asl",
        "ats",
        "agenzia",
        "entrate",
        "ufficio",
        "municipio",
        "stato",
        "civile",
        "the",
        "i",
        "il",
        "la",
        "lo",
        "le",
        "gli",
    }
)
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ']+")
_SENTENCE_END = re.compile(r"[.!?:]\s*$")

# Indizi di tono (minuscolo, it/en); servono solo senza modello.
_POSITIVE_HINTS = ("grazie", "perfetto", "ottimo", "thank", "great", "perfect")
_FRUSTRATED_HINTS = (
    "inutile",
    "assurd",
    "ridicol",
    "arrabbiat",
    "vergogn",
    "frustrat",
    "useless",
    "angry",
    "absurd",
    "ridiculous",
)

SYSTEM_PROMPT = """Ricevi il commento di un cittadino dopo un appuntamento all'anagrafe di Milano.
Il commento e' gia' stato ripulito da email, telefoni e documenti.
Rispondi SOLO con un oggetto JSON con questi campi:
- "missing_requirement": il documento o requisito che mancava, in forma generica, oppure null;
- "probable_cause": una tra "pagina-incompleta", "procedura-non-aggiornata",
  "procedura-mancante", "ente-o-ufficio-sbagliato", "pagina-chiara-non-seguita",
  "richiesta-non-prevista", oppure null;
- "tone": "neutro", "frustrato" o "positivo";
- "suggestion": un suggerimento generalizzato per migliorare la pagina, oppure null.
Non riportare mai nomi di persone, indirizzi, date precise o altri dettagli identificativi.
Scrivi in italiano."""


class ClaudeClient(Protocol):
    """Dipendenza minima verso Claude: un prompt di sistema e un testo, risposta testuale."""

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
        """Restituisce il testo della risposta del modello."""
        ...


class StructuredFeedback(BaseModel):
    """L'unico risultato salvabile del feedback libero."""

    model_config = ConfigDict(frozen=True)

    missing_requirement: str | None = None
    probable_cause: Cause | None = None
    tone: Tone = "neutro"
    suggestion: str | None = None


def _guess_tone(text: str) -> Tone:
    lowered = text.lower()
    if any(hint in lowered for hint in _FRUSTRATED_HINTS):
        return "frustrato"
    if any(hint in lowered for hint in _POSITIVE_HINTS):
        return "positivo"
    return "neutro"


def name_like_tokens(text: str) -> frozenset[str]:
    """Parole con iniziale maiuscola non a inizio frase: possibili nomi propri."""
    tokens: set[str] = set()
    for match in _WORD.finditer(text):
        word = match.group(0)
        if not word[:1].isupper() or word.lower() in _ALLOWED_CAPITALISED:
            continue
        before = text[: match.start()].rstrip()
        if not before or _SENTENCE_END.search(before + " "):
            continue
        tokens.add(word.lower())
    return frozenset(tokens)


def _clean_field(value: str | None, banned: frozenset[str]) -> str | None:
    """Scarta un campo con dati personali o con possibili nomi del testo originale."""
    if value is None:
        return None
    candidate = value.strip()[:MAX_FIELD_CHARS]
    if not candidate or contains_pii(candidate):
        return None
    words = {w.lower() for w in _WORD.findall(candidate)}
    if words & banned:
        return None
    return candidate


def _parse_model_json(raw: str) -> dict[str, object] | None:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def structure_feedback(
    text: str, *, client: ClaudeClient | None = None, model: str = DEFAULT_MODEL
) -> StructuredFeedback:
    """Trasforma un commento libero in campi strutturati generalizzati.

    Passo 1 (sempre): espressioni regolari. Passo 2 (se ``client`` non e' None):
    Claude riceve solo il testo ripulito. Il testo originale non viene restituito.
    """
    redacted = redact(text).text
    fallback = StructuredFeedback(tone=_guess_tone(redacted))
    if client is None:
        return fallback
    try:
        raw = client.complete(
            model=model, system=SYSTEM_PROMPT, prompt=redacted, max_tokens=MAX_TOKENS
        )
    except ClaudeUnavailableError:
        # L'esito si registra comunque: senza Claude restano i campi della regola.
        return fallback
    data = _parse_model_json(raw)
    if data is None:
        return fallback
    try:
        parsed = StructuredFeedback.model_validate(data)
    except ValidationError:
        return fallback
    banned = name_like_tokens(text)
    return StructuredFeedback(
        missing_requirement=_clean_field(parsed.missing_requirement, banned),
        probable_cause=parsed.probable_cause,
        tone=parsed.tone,
        suggestion=_clean_field(parsed.suggestion, banned),
    )
