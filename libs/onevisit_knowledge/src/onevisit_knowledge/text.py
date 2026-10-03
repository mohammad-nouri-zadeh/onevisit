"""Testo delle pagine salvate: front matter YAML, normalizzazione, hash (storie A1, C4).

Le pagine in ``data/pages/<source_id>.md`` possono avere un front matter YAML
(scritto da ``onevisit ingest``) oppure il commento HTML iniziale di
``data/tools/save_page.py``. Le citazioni si cercano sempre nel solo corpo.
"""

import hashlib
import re
from typing import Any

import yaml

# Delimitatore del front matter YAML, come in Jekyll/Hugo.
FRONT_MATTER_DELIMITER = "---"

_QUOTE_MAP = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"'})
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Normalizza come ``data/tools/validate.py``: apostrofi, spazi, minuscole."""
    return _SPACES.sub(" ", text.translate(_QUOTE_MAP)).strip().lower()


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Separa il front matter YAML dal corpo; senza front matter restituisce ``({}, testo)``."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        return {}, text
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONT_MATTER_DELIMITER:
            raw = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            try:
                meta = yaml.safe_load(raw) or {}
            except yaml.YAMLError:
                return {}, text
            return (meta if isinstance(meta, dict) else {}), body.lstrip("\n")
    return {}, text


def content_hash(body: str) -> str:
    """Hash SHA-256 del corpo della pagina, con prefisso ``sha256:``."""
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def render_page(meta: dict[str, Any], body: str) -> str:
    """Compone front matter YAML e corpo Markdown."""
    header = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    return f"{FRONT_MATTER_DELIMITER}\n{header}\n{FRONT_MATTER_DELIMITER}\n\n{body}"
