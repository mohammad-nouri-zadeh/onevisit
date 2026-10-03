"""Validatore delle risposte dell'agente (storia C3).

Blocca: citazioni con ``source_id`` inesistente, parole che dichiarano l'idoneità
(it/en/es/fr/pt/ar, tutte le lingue del prompt di sistema; parola intera, senza
distinguere maiuscole e accenti) e risposte senza citazioni quando il turno ha usato
fatti del catalogo. Restituisce codici di motivo, mai il testo della risposta.
"""

import re
import unicodedata

CITATION_RE = re.compile(r"\[fonte:\s*([A-Za-z0-9_.\-]+)\s*\]", re.IGNORECASE)

# Parole e frasi vietate, già senza accenti e in minuscolo (il testo viene normalizzato uguale).
FORBIDDEN_PHRASES: tuple[str, ...] = (
    # italiano
    "idoneo",
    "idonea",
    "idonei",
    "idonee",
    "in regola",
    "garantito",
    "garantita",
    "garantiti",
    "garantite",
    # inglese
    "eligible",
    "guaranteed",
    "compliant",
    "you qualify",
    "you are qualified",
    # spagnolo
    "elegible",
    "garantizado",
    "garantizada",
    "en regla",
    "apto",
    "apta",
    # francese (éligible e garanti senza accenti)
    "eligible",
    "garanti",
    "garantie",
    "en regle",
    # portoghese
    "elegivel",
    "garantido",
    "garantida",
    "em regra",
    # arabo: idoneo/idonea, garantito/garantita
    "مؤهل",
    "مؤهلة",
    "مضمون",
    "مضمونة",
)


def _fold(text: str) -> str:
    """Minuscolo e senza accenti, per un confronto tollerante."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


# Anche le frasi passano da _fold: in arabo NFKD separa la hamza, che va tolta come il testo.
_FORBIDDEN_RE = re.compile(
    r"\b("
    + "|".join(
        re.escape(p).replace(r"\ ", r"\s+") for p in sorted({_fold(x) for x in FORBIDDEN_PHRASES})
    )
    + r")\b"
)


def cited_source_ids(text: str) -> list[str]:
    """Gli ``source_id`` citati nel formato ``[fonte: <id>]``."""
    return [match.group(1) for match in CITATION_RE.finditer(text)]


def forbidden_phrases_in(text: str) -> list[str]:
    """Le frasi vietate presenti (normalizzate), in ordine di comparsa."""
    return [match.group(1) for match in _FORBIDDEN_RE.finditer(_fold(text))]


def validate_reply(text: str, *, known_source_ids: frozenset[str], used_facts: bool) -> list[str]:
    """Restituisce i motivi del blocco; lista vuota se la risposta può andare al cittadino."""
    reasons: list[str] = []
    cited = cited_source_ids(text)
    reasons.extend(
        f"unknown_source:{source_id}" for source_id in cited if source_id not in known_source_ids
    )
    reasons.extend(f"forbidden_phrase:{phrase}" for phrase in forbidden_phrases_in(text))
    if used_facts and not cited:
        reasons.append("missing_citation")
    return reasons
