"""Primo passaggio deterministico della pipeline privacy (storia C9).

Espressioni regolari per email, numeri di telefono, codici fiscali, IBAN e numeri
dei documenti piu' comuni. Ogni valore trovato e' sostituito da un segnaposto.
Date (03/10/2026, 2026-10-03) e orari (10:30) non vengono toccati.
"""

import re
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

# Segnaposto per categoria: le categorie restituite in Redaction.found sono le chiavi.
PLACEHOLDERS: dict[str, str] = {
    "email": "[EMAIL]",
    "iban": "[IBAN]",
    "codice_fiscale": "[CODICE_FISCALE]",
    "documento": "[DOCUMENTO]",
    "telefono": "[TELEFONO]",
}

# Cifre minime e massime di un numero internazionale (E.164 arriva a 15 cifre).
_INTL_MIN_DIGITS = 8
_INTL_MAX_DIGITS = 15
# Numeri italiani senza prefisso: fissi e cellulari hanno da 9 a 11 cifre.
_IT_MIN_DIGITS = 9
_IT_MAX_DIGITS = 11
# Un numero di documento citato dopo una parola chiave contiene almeno 4 cifre.
_DOC_MIN_DIGITS = 4


class Redaction(BaseModel):
    """Testo ripulito e categorie di dati personali trovate."""

    model_config = ConfigDict(frozen=True)

    text: str
    found: list[str]


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

# IBAN italiano (27 caratteri), anche minuscolo e con spazi.
_IBAN_IT = re.compile(r"\bit\s?\d{2}\s?[a-z](?:\s?[0-9a-z]){22}\b", re.IGNORECASE)
# IBAN generico: paese, controllo, poi gruppi da quattro con spazi facoltativi.
_IBAN_GENERIC = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")

# Codice fiscale: 16 caratteri; lettere di omocodia ammesse nelle posizioni numeriche.
_L = "[A-Za-z]"
_D = "[0-9LMNPQRSTUVlmnpqrstuv]"
_M = "[ABCDEHLMPRSTabcdehlmprst]"
_CF_PARTS = [_L] * 6 + [_D] * 2 + [_M] + [_D] * 2 + [_L] + [_D] * 3 + [_L]
_CODICE_FISCALE = re.compile(r"\b" + r" ?".join(_CF_PARTS) + r"\b")

# Documenti: CIE (CA00000AA), passaporto (YA0000000), permesso elettronico (I00000000).
_CIE = re.compile(r"\b[A-Z]{2}\d{5}[A-Z]{2}\b", re.IGNORECASE)
_PASSPORT = re.compile(r"\b[A-Z]{2} ?\d{7}\b", re.IGNORECASE)
_PERMIT = re.compile(r"\b[A-Z]\d{8}\b", re.IGNORECASE)
# Numero citato dopo il nome del documento ("permesso di soggiorno n. 0000000000").
_DOC_CONTEXT = re.compile(
    r"\b(?:permesso(?: di soggiorno)?|residence permit|passaporto|passport|"
    r"carta d.identit[aà]|identity card|documento|document)\b[^\n\d]{0,25}?"
    r"(?P<num>[A-Z0-9][A-Z0-9-]{5,14})\b",
    re.IGNORECASE,
)

# Candidati telefono: cifre con spazi, punti, trattini o parentesi.
_PHONE_CANDIDATE = re.compile(r"(?<![\w/:])(?:\+|00)?\d[\d \t().-]{5,20}\d(?![\w/:])")
_DATE_LIKE = re.compile(r"^\d{1,4}[./-]\d{1,2}[./-]\d{1,4}$")


def _digits(value: str) -> int:
    return sum(ch.isdigit() for ch in value)


def _is_phone(candidate: str) -> bool:
    """Decide se un candidato e' un telefono, escludendo date e importi."""
    stripped = candidate.strip()
    if _DATE_LIKE.match(stripped):
        return False
    count = _digits(stripped)
    if stripped.startswith(("+", "00")):
        return _INTL_MIN_DIGITS <= count <= _INTL_MAX_DIGITS
    first = stripped.lstrip("(")[:1]
    return first in {"0", "3"} and _IT_MIN_DIGITS <= count <= _IT_MAX_DIGITS


def _sub(
    pattern: re.Pattern[str],
    category: str,
    text: str,
    found: list[str],
    accept: Callable[[re.Match[str]], bool] | None = None,
) -> str:
    placeholder = PLACEHOLDERS[category]
    hit = False

    def repl(match: re.Match[str]) -> str:
        nonlocal hit
        if accept is not None and not accept(match):
            return match.group(0)
        hit = True
        return placeholder

    result = pattern.sub(repl, text)
    if hit and category not in found:
        found.append(category)
    return result


def _sub_doc_context(text: str, found: list[str]) -> str:
    hit = False

    def repl(match: re.Match[str]) -> str:
        nonlocal hit
        number = match.group("num")
        if _digits(number) < _DOC_MIN_DIGITS:
            return match.group(0)
        hit = True
        start, end = match.span("num")
        offset = match.start()
        whole = match.group(0)
        return whole[: start - offset] + PLACEHOLDERS["documento"] + whole[end - offset :]

    result = _DOC_CONTEXT.sub(repl, text)
    if hit and "documento" not in found:
        found.append("documento")
    return result


def redact(text: str) -> Redaction:
    """Sostituisce i dati personali riconoscibili con segnaposto."""
    found: list[str] = []
    out = _sub(_EMAIL, "email", text, found)
    out = _sub(_IBAN_IT, "iban", out, found)
    out = _sub(_IBAN_GENERIC, "iban", out, found, lambda m: _digits(m.group(0)) >= _DOC_MIN_DIGITS)
    out = _sub(_CODICE_FISCALE, "codice_fiscale", out, found)
    out = _sub(_CIE, "documento", out, found)
    out = _sub(_PASSPORT, "documento", out, found)
    out = _sub(_PERMIT, "documento", out, found)
    out = _sub_doc_context(out, found)
    out = _sub(_PHONE_CANDIDATE, "telefono", out, found, lambda m: _is_phone(m.group(0)))
    return Redaction(text=out, found=found)


def contains_pii(text: str) -> bool:
    """Vero se il testo contiene almeno un dato personale riconoscibile."""
    return bool(redact(text).found)
