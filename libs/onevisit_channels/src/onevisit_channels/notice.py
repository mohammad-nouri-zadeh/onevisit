"""Informativa breve sulla privacy (storia A4).

Il testo sta in ``messages/informativa.<lingua>.md`` e dice esplicitamente che il
cittadino parla con un'intelligenza artificiale.
"""

from functools import lru_cache
from pathlib import Path

from onevisit_channels.errors import TemplateNotFoundError
from onevisit_channels.models import SUPPORTED_LANGUAGES

MESSAGES_DIR = Path(__file__).parent / "messages"


@lru_cache(maxsize=len(SUPPORTED_LANGUAGES))
def informativa(language: str) -> str:
    """Restituisce l'informativa in Markdown (inglese se la lingua non e' disponibile)."""
    base = language.lower().split("-")[0]
    lang = base if base in SUPPORTED_LANGUAGES else "en"
    path = MESSAGES_DIR / f"informativa.{lang}.md"
    if not path.is_file():
        raise TemplateNotFoundError(f"informativa mancante: {lang}")
    return path.read_text(encoding="utf-8")
