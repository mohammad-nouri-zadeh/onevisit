"""Resa sicura del Markdown delle risposte e dei link alle fonti (storie B3, C3).

Prima si fa l'escape di tutto il testo, poi si trasformano poche forme note
(grassetto, corsivo, elenchi, a capo, link http/https, citazioni ``[fonte: id]``).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from markupsafe import Markup, escape

_CITATION_RE = re.compile(r"\[(?:fonte|source):\s*([A-Za-z0-9._-]+)\]")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_URL_RE = re.compile(r"(?<![\"'=>])(https?://[^\s<]+[^\s<.,;:!?)])")
_BULLET_RE = re.compile(r"^\s*[-*•]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")


@dataclass(frozen=True)
class SourceLink:
    """Dati mostrati per una fonte citata."""

    title: str
    url: str
    verified_on: str | None


SourceLookup = Callable[[str], SourceLink | None]


def _inline(text: str, lookup: SourceLookup, labels: dict[str, str]) -> str:
    """Escape e trasformazioni in linea di una riga."""
    html = str(escape(text))
    html = _LINK_RE.sub(r'<a href="\2" rel="noopener" target="_blank">\1</a>', html)
    html = _URL_RE.sub(r'<a href="\1" rel="noopener" target="_blank">\1</a>', html)
    html = _BOLD_RE.sub(r"<strong>\1</strong>", html)
    html = _ITALIC_RE.sub(r"<em>\1</em>", html)

    def citation(match: re.Match[str]) -> str:
        source = lookup(match.group(1))
        if source is None or not source.url:
            return str(escape(f"[{labels['source']}: {match.group(1)}]"))
        source_id = match.group(1)
        detail = f"{source.title}"
        if source.verified_on:
            detail += f" ({labels['verified_on']} {source.verified_on})"
        # Testo breve e monospaziato (fonte + id); titolo e data nel nome accessibile e
        # nel title, che contengono il testo visibile (WCAG 2.5.3).
        name = f"{labels['source']} {source_id}: {detail}"
        return (
            f'<a class="cite" href="{escape(source.url)}" rel="noopener" target="_blank"'
            f' title="{escape(name)}" aria-label="{escape(name)}">'
            f"{escape(labels['source'])} {escape(source_id)}</a>"
        )

    return _CITATION_RE.sub(citation, html)


def render_markdown(text: str, lookup: SourceLookup, labels: dict[str, str]) -> Markup:
    """Converte il Markdown limitato dell'agente in HTML sicuro."""
    out: list[str] = []
    list_tag: str | None = None
    for line in text.splitlines():
        bullet = _BULLET_RE.match(line)
        numbered = None if bullet else _NUMBERED_RE.match(line)
        item = bullet or numbered
        tag = "ul" if bullet else "ol" if numbered else None
        if list_tag and tag != list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None
        if item and tag:
            if list_tag is None:
                out.append(f"<{tag}>")
                list_tag = tag
            out.append(f"<li>{_inline(item.group(1), lookup, labels)}</li>")
        elif line.strip():
            out.append(f"<p>{_inline(line, lookup, labels)}</p>")
    if list_tag:
        out.append(f"</{list_tag}>")
    # Ogni frammento e' gia' passato da escape() in _inline: il Markup e' sicuro.
    return Markup("\n".join(out))  # noqa: S704
