"""Testi rivolti al cittadino in italiano e inglese e scelta della lingua (storie B1, B2).

I testi stanno in ``templates/messages/<lingua>.json``: qui solo il caricamento.
"""

import json
from functools import cache
from pathlib import Path

MESSAGES_DIR = Path(__file__).parent / "templates" / "messages"
SUPPORTED = ("it", "en")
DEFAULT_LANGUAGE = "it"
# Cookie con la lingua scelta dal menu (``?lang=it|en``): prevale su Accept-Language.
LANG_COOKIE = "ov_lang"
LANG_COOKIE_MAX_AGE_S = 60 * 60 * 24 * 180


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


def chosen_language(query: str | None, cookie: str | None) -> str | None:
    """Lingua scelta esplicitamente: ``?lang=`` della richiesta, poi il cookie; o ``None``."""
    for value in (query, cookie):
        if value and value.strip().lower() in SUPPORTED:
            return value.strip().lower()
    return None
