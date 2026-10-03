"""Testi rivolti al cittadino in italiano e inglese e scelta della lingua (storie B1, B2).

I testi stanno in ``templates/messages/<lingua>.json``: qui solo il caricamento.
"""

import json
from functools import cache
from pathlib import Path

MESSAGES_DIR = Path(__file__).parent / "templates" / "messages"
SUPPORTED = ("it", "en")
DEFAULT_LANGUAGE = "it"


@cache
def messages(language: str) -> dict[str, str]:
    """Testi dell'interfaccia nella lingua indicata (inglese per le lingue non italiane)."""
    lang = ui_language(language)
    data: dict[str, str] = json.loads((MESSAGES_DIR / f"{lang}.json").read_text("utf-8"))
    return data


def ui_language(language: str | None) -> str:
    """Lingua dell'interfaccia: italiano per ``it``, inglese per ogni altra lingua nota."""
    if not language:
        return DEFAULT_LANGUAGE
    base = language.lower().split("-")[0].strip()
    return "it" if base == "it" else "en"


def browser_language(accept_language: str | None) -> str:
    """Prima lingua supportata di ``Accept-Language``; italiano se nessuna."""
    if not accept_language:
        return DEFAULT_LANGUAGE
    for part in accept_language.split(","):
        tag = part.split(";")[0].strip().lower().split("-")[0]
        if tag in SUPPORTED:
            return tag
    return DEFAULT_LANGUAGE
