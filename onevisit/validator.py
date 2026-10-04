"""Automatic check on every answer before the citizen sees it.

Port of the kit's validator (libs/onevisit_agent/src/onevisit_agent/validator.py)
for the Streamlit app. It blocks a reply when:

(a) it cites a source id that is not in the catalogue (data/sources.csv), or that
    no tool returned in this conversation (Claude may cite only what it has read);
(b) it says or implies that the person or their documents are eligible, valid,
    in order or guaranteed (it, en, es, fr, pt, ar, zh): the desk officer decides;
(c) it uses checklist or office facts without citing a single source.

It returns short reason codes, never the reply text, so nothing the citizen wrote
ends up in logs. The agent regenerates once with the reasons; if the second reply
is blocked too, the citizen gets a safe fallback with the official page.

    from onevisit import validator
    reasons = validator.check_reply(text, known_ids=..., read_ids=..., used_facts=True)
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable

# A citation is a source id in square brackets: [ds549], [cie], [fonte: cie], [cie, ds549].
# "(?!\()" skips Markdown links like [text](url).
_BRACKET_RE = re.compile(r"\[([^\[\]\n]{1,120})\](?!\()")
_PREFIX_RE = re.compile(r"^(?:fonte|fonti|source|sources|fuente|fuentes|المصدر|来源)\s*[:：]\s*", re.IGNORECASE)
_ID_SHAPE = re.compile(r"^[a-z0-9]+(?:[-_.][a-z0-9]+)*$")

# Phrases that claim eligibility or validity. Written already folded: lower case, no accents
# (the text is folded the same way). Matched as whole words, except Chinese (no spaces).
FORBIDDEN_PHRASES: dict[str, tuple[str, ...]] = {
    "it": ("idoneo", "idonea", "idonei", "idonee", "in regola", "garantito", "garantita", "garantiti",
           "garantite", "ti garantisco", "documenti validi", "documentazione valida", "documentazione completa",
           "hai tutto il necessario", "hai tutto quello che serve", "sei a posto", "verra accettato",
           "verra accettata", "verranno accettati", "sara accettato", "sara accettata", "saranno accettati",
           "andra a buon fine"),
    "en": ("eligible", "guaranteed", "guarantee", "you qualify", "you are qualified", "you are all set",
           "you're all set", "you have everything you need", "documents are valid", "documents are sufficient",
           "will be accepted", "compliant"),
    "es": ("elegible", "garantizado", "garantizada", "te lo garantizo", "en regla", "cumples los requisitos",
           "cumples", "documentos validos", "documentos son validos", "sera aceptado", "seran aceptados",
           "tienes todo lo necesario", "apto", "apta"),
    "fr": ("garanti", "garantie", "en regle", "vous remplissez les conditions", "documents sont valides",
           "documents valides", "sera accepte", "seront acceptes", "vous avez tout ce qu'il faut"),
    "pt": ("elegivel", "garantido", "garantida", "em regra", "documentos validos", "documentos sao validos"),
    "ar": ("مؤهل", "مؤهلة", "مضمون", "مضمونة", "نضمن", "اضمن", "وثائقك صالحة", "مستنداتك صالحة",
           "اوراقك صالحة", "وثائقك مكتملة", "مستنداتك مكتملة", "سيتم قبول", "ستقبل"),
    "zh": ("符合条件", "有资格", "保证", "材料有效", "文件有效", "证件有效", "一定会通过", "肯定会通过", "合格"),
}

# "Your <document> is valid / sufficient / complete" in it, en, es, fr.
_VALIDITY_RES = (
    re.compile(r"\b(?:il tuo|la tua|i tuoi|le tue|tuo|tua|tuoi|tue)\s+\w+(?:\s+\w+)?\s+(?:e|sono|risulta|risultano)\s+"
               r"(?:valid[oaie]|sufficient[ei]|complet[oaie]|corrett[oaie])\b"),
    re.compile(r"\byour\s+\w+(?:\s+\w+)?\s+(?:is|are|looks|look)\s+(?:valid|sufficient|complete|correct|fine|enough)\b"),
    re.compile(r"\b(?:tu|tus)\s+\w+\s+(?:es|son|esta|estan)\s+(?:valid[oa]s?|suficientes?|complet[oa]s?)\b"),
    re.compile(r"\b(?:ton|ta|tes|votre|vos)\s+\w+\s+(?:est|sont)\s+(?:valides?|suffisante?s?|complete?s?)\b"),
)

_CJK = re.compile(r"[㐀-鿿]")


def fold(text: str) -> str:
    """Lower case without accents (Arabic hamza forms fold to the bare letter)."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _phrase_re() -> re.Pattern[str]:
    words = sorted({fold(p) for lang, ps in FORBIDDEN_PHRASES.items() if lang != "zh" for p in ps}, key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in words) + r")(?!\w)")


_FORBIDDEN_RE = _phrase_re()


def forbidden_phrases_in(text: str) -> list[str]:
    """Eligibility or validity claims in the text, folded, in order of appearance."""
    folded = fold(text)
    found = [m.group(1) for m in _FORBIDDEN_RE.finditer(folded)]
    found += [m.group(0) for r in _VALIDITY_RES for m in r.finditer(folded)]
    found += [p for p in FORBIDDEN_PHRASES["zh"] if p in text]
    return found


def cited_source_ids(text: str, known_ids: Iterable[str] = ()) -> list[str]:
    """Source ids cited in square brackets, in order, without duplicates.

    A bracketed word counts as a citation when it is a catalogue id, when it follows
    "fonte:"/"source:", or when it looks like an id (letters with digits, '-', '_' or
    '.'), so an invented id like [ds123] or [cie-2024] is caught. Plain words such as
    "[note]" are not citations.
    """
    known = set(known_ids)
    out: list[str] = []
    for m in _BRACKET_RE.finditer(text):
        inner = m.group(1).strip()
        prefixed = bool(_PREFIX_RE.match(inner))
        inner = _PREFIX_RE.sub("", inner)
        for part in re.split(r"\s*[,;，、]\s*", inner):
            token = part.strip().strip("`")
            if not token or not _ID_SHAPE.match(token) or not re.search(r"[a-z]", token):
                continue
            looks_like_id = bool(re.search(r"[0-9\-_.]", token))
            if (token in known or prefixed or looks_like_id) and token not in out:
                out.append(token)
    return out


def sources_in(obj: object) -> set[str]:
    """Every source id inside a tool result: source_id fields, source_ids lists,
    the 'sources' list of get_checklist and the record returned by get_source."""
    found: set[str] = set()
    if isinstance(obj, dict):
        if isinstance(obj.get("source_id"), str):
            found.add(obj["source_id"])
        if isinstance(obj.get("source_ids"), list):
            found.update(s for s in obj["source_ids"] if isinstance(s, str))
        if {"id", "url", "publisher"} <= obj.keys() and isinstance(obj["id"], str):
            found.add(obj["id"])
        for value in obj.values():
            found |= sources_in(value)
    elif isinstance(obj, list):
        for value in obj:
            found |= sources_in(value)
    return found


def sources_in_trace(trace: list[dict]) -> set[str]:
    """Source ids returned by the tool calls of one turn."""
    found: set[str] = set()
    for step in trace:
        found |= sources_in(step.get("output"))
    return found


def sources_in_messages(messages: list) -> set[str]:
    """Source ids returned by tools earlier in the API history (tool_result blocks)."""
    found: set[str] = set()
    for m in messages:
        content = m.get("content") if isinstance(m, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                raw = block.get("content")
                try:
                    found |= sources_in(json.loads(raw) if isinstance(raw, str) else raw)
                except (TypeError, ValueError):
                    continue
    return found


def _is_question_only(text: str) -> bool:
    """A short reply that only asks the next question carries no facts to cite."""
    stripped = text.strip()
    return len(stripped) <= 240 and stripped.endswith(("?", "؟", "？"))


def used_facts(trace: list[dict], text: str) -> bool:
    """True when this turn's tools returned requirements, steps or offices and the
    reply is more than a short question (so it presents those facts)."""
    if _is_question_only(text):
        return False
    for step in trace:
        out = step.get("output")
        if isinstance(out, dict) and (out.get("requirements") or out.get("steps") or out.get("sections")):
            return True
        if step.get("tool") == "find_offices" and isinstance(out, list) and out:
            return True
    return False


def check_reply(text: str, *, known_ids: Iterable[str], read_ids: Iterable[str], used_facts: bool) -> list[str]:
    """Reasons to block the reply; an empty list means it can reach the citizen."""
    known, read = set(known_ids), set(read_ids)
    reasons: list[str] = []
    cited = cited_source_ids(text, known)
    for sid in cited:
        if sid not in known:
            reasons.append(f"unknown_source:{sid}")
        elif sid not in read:
            reasons.append(f"source_not_read:{sid}")
    reasons += [f"eligibility_claim:{p}" for p in dict.fromkeys(forbidden_phrases_in(text))]
    if used_facts and not cited:
        reasons.append("missing_citation")
    return reasons


_DESCRIBE = {
    "it": {"unknown_source": "fonte inesistente", "source_not_read": "fonte non letta in questa conversazione",
           "eligibility_claim": "parola che promette l'esito", "missing_citation": "fatti senza fonte"},
    "en": {"unknown_source": "unknown source", "source_not_read": "source not read in this conversation",
           "eligibility_claim": "word that promises the outcome", "missing_citation": "facts without a source"},
}


def describe(reasons: list[str], lang: str = "en") -> str:
    """Short human-readable summary of the reasons (Italian or English)."""
    labels = _DESCRIBE.get(lang, _DESCRIBE["en"])
    parts = []
    for r in reasons:
        code, _, detail = r.partition(":")
        label = labels.get(code, code)
        parts.append(f"{label} ({detail})" if detail and code != "eligibility_claim" else
                     (f"{label}: “{detail}”" if detail else label))
    return "; ".join(dict.fromkeys(parts))


def retry_instruction(reasons: list[str]) -> str:
    """The message the agent sends back to Claude when a reply is blocked."""
    return (
        "AUTOMATIC CHECK (this message is from the OneVisit validator, not from the citizen). "
        "Your last reply was blocked before reaching the citizen for these reasons: "
        + "; ".join(reasons) + ". "
        "Write the reply again, in the same language as the citizen, following the rules: "
        "cite in square brackets only source ids that a tool returned in this conversation, like [ds549]; "
        "every requirement, office, hour or cost you mention needs its source id; "
        "never say or imply that the person or their documents are eligible, valid, complete, in order, "
        "accepted or guaranteed, not even in a negative sentence: say that the officer at the desk decides. "
        "Do not mention this check."
    )
