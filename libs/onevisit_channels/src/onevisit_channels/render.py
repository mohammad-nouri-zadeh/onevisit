"""Composizione dei messaggi dai modelli Jinja2 (storie C6, C7, B7).

I modelli hanno solo due segnaposto, ``days_left`` e ``link`` (piu' ``consents_link``
per l'email). Non nominano mai il servizio: chi legge lo schermo bloccato del
telefono non deve capire di quale pratica si tratta.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
    select_autoescape,
)

from onevisit_channels.errors import TemplateNotFoundError
from onevisit_channels.models import SUPPORTED_LANGUAGES, RenderedMessage

TEMPLATES_DIR = Path(__file__).parent / "templates"
FALLBACK_LANGUAGE = "en"


@lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(enabled_extensions=("html",), default=False),
        undefined=StrictUndefined,
        keep_trailing_newline=False,
    )


def _language(language: str) -> str:
    base = language.lower().split("-")[0]
    return base if base in SUPPORTED_LANGUAGES else FALLBACK_LANGUAGE


def _render(name: str, context: dict[str, object]) -> str:
    try:
        template = _environment().get_template(name)
    except TemplateNotFound:
        raise TemplateNotFoundError(f"modello mancante: {name}") from None
    return template.render(**context).strip()


def render_notification(
    kind: str,
    *,
    language: str,
    channel: Literal["email", "sms"],
    days_left: int | None,
    link: str,
    consents_link: str | None = None,
) -> RenderedMessage:
    """Compone il messaggio di ``kind`` nella lingua del cittadino (italiano o inglese)."""
    lang = _language(language)
    context: dict[str, object] = {
        "days_left": days_left,
        "link": link,
        "consents_link": consents_link or link,
    }
    if channel == "sms":
        return RenderedMessage(
            subject=None, text=_render(f"sms/{kind}.{lang}.txt", context), html=None
        )
    subject = _render(f"email/{kind}.{lang}.subject.txt", context)
    text = _render(f"email/{kind}.{lang}.txt", context)
    html = _render(f"email/{kind}.{lang}.html", context)
    return RenderedMessage(subject=subject, text=text, html=html)
