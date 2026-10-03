"""Controllo dei nomi propri nei campi salvati delle lacune (storia C10).

Le lacune sono aggregate per procedura e per sede, mai per persona: prima di salvare
titolo, riassunto, esempi e bozze si rifiuta ogni parola che sembra un nome proprio.
Il controllo e' volutamente prudente: meglio scartare un testo di Claude e usare la
regola di riserva che salvare il nome di un cittadino o di un dipendente.
"""

import re
from collections.abc import Iterable

from onevisit_analytics.errors import ProperNameError

# Parole con iniziale maiuscola ammesse a meta' frase: istituzioni, luoghi, documenti.
ALLOWED_CAPITALIZED = frozenset(
    {
        "Comune",
        "Milano",
        "Italia",
        "Questura",
        "Polizia",
        "Stato",
        "Agenzia",
        "Entrate",
        "Anagrafe",
        "Municipio",
        "Prefettura",
        "Repubblica",
        "Unione",
        "Europea",
        "UE",
        "CIE",
        "SPID",
        "CIE.",
        "OneVisit",
        "Italian",
        "English",
        "Easy",
        "Milan",
        "City",
        "Registry",
        "Office",
        "Police",
        "Revenue",
        "Agency",
        "EU",
        "Italy",
        "Municipality",
    }
)
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ'][\wÀ-ÖØ-öø-ÿ'-]*")
_SENTENCE_END = re.compile(r"[.!?:;\n\"«(\[]\s*$")


def find_proper_names(text: str) -> list[str]:
    """Parole con iniziale maiuscola a meta' frase, non presenti nell'elenco ammesso."""
    found: list[str] = []
    for match in _WORD.finditer(text):
        word = match.group(0)
        if not word[0].isupper() or word.isupper() or word in ALLOWED_CAPITALIZED:
            continue
        before = text[: match.start()]
        if not before.strip() or _SENTENCE_END.search(before):
            continue
        found.append(word)
    return found


def ensure_no_proper_names(fields: Iterable[str | None]) -> None:
    """Solleva :class:`ProperNameError` se un campo contiene un probabile nome proprio.

    Il messaggio non riporta la parola trovata, perche' potrebbe essere un dato personale.
    """
    for value in fields:
        if value and find_proper_names(value):
            raise ProperNameError("campo con un probabile nome proprio: testo scartato")
