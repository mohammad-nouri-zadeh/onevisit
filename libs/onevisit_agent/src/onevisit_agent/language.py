"""Lingua del turno e risposte rapide dai marcatori nascosti (storia B2).

Il prompt chiede al modello di cominciare la risposta con ``<lang>xx</lang>`` (ISO 639-1) e,
se servono, di chiudere con ``<quick>a | b</quick>``. Qui i marcatori si leggono e si tolgono.
"""

import re
from dataclasses import dataclass

DEFAULT_LANGUAGE = "it"
_LANG_RE = re.compile(r"<lang>\s*([A-Za-z]{2})\s*</lang>", re.IGNORECASE)
_QUICK_RE = re.compile(r"<quick>(.*?)</quick>", re.IGNORECASE | re.DOTALL)
# Numero massimo di risposte rapide mostrate come pulsanti.
MAX_QUICK_REPLIES = 4


@dataclass(frozen=True)
class ParsedReply:
    """Risposta ripulita dai marcatori."""

    text: str
    language: str | None
    quick_replies: list[str]


def parse_reply(raw: str) -> ParsedReply:
    """Estrae lingua e risposte rapide e restituisce il testo senza marcatori."""
    lang_match = _LANG_RE.search(raw)
    language = lang_match.group(1).lower() if lang_match else None
    quick: list[str] = []
    for match in _QUICK_RE.finditer(raw):
        quick.extend(part.strip() for part in match.group(1).split("|") if part.strip())
    text = _QUICK_RE.sub("", _LANG_RE.sub("", raw)).strip()
    return ParsedReply(text=text, language=language, quick_replies=quick[:MAX_QUICK_REPLIES])


def initial_language(browser_language: str | None) -> str:
    """Lingua di partenza: quella del browser (prime due lettere), altrimenti l'italiano."""
    if browser_language:
        code = browser_language.strip()[:2].lower()
        if code.isalpha() and len(code) == 2:
            return code
    return DEFAULT_LANGUAGE
