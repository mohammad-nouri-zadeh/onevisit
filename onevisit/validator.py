"""Automatic check on every answer before the citizen sees it.

Port of the kit's validator (libs/onevisit_agent/src/onevisit_agent/validator.py)
for the Streamlit app. It blocks a reply when:

(a) it cites a source id that is not in the catalogue (data/sources.csv), or that
    no tool returned in this conversation (Claude may cite only what it has read;
    search_official_pages and read_source count);
(b) it says or implies that the person or their documents are eligible, valid,
    in order or guaranteed (it, en, es, fr, pt, ar, zh): the desk officer decides.
    Only the reply's own words are checked: a verified quote of an official page that
    is a sentence (six words, or a whole sentence or line of the page) may say "valido"
    or "in regola" in the page's own sense; a one-word «idonea» is the reply's own word.
    Quotation marks never hide words («è valido»), and "your card: «...è valida»" is
    caught across the quote;
(c) it states facts without citing a source: after the tools returned checklist, office
    or passage facts, or whenever it has digits, amounts or links (a fee from memory);
(d) a quote (« », and “ ”, " ", „ “, 「」, 『』, ‹ › or a '>' line when a citation follows
    or it has four words) is not a verbatim slice of official text a tool returned in
    this conversation (search passages, read_source passages, the verbatim quotes of
    checklist items): "invented_quote:<n>"; or it is, but not of the source cited right
    after it: "quote_source_mismatch:<id>". Spacing, Markdown, list marks, typographic
    quotes and case don't count; the quote must start and end on word boundaries, keep a
    question's "?", and "..." or "[…]" may skip words only inside one paragraph, at most
    twice, each part four words or more (an ellipsis can't drop a "non"). An uncited quote
    of at most three words and no digits is a term ("Procedi senza registrazione"): not
    blocked, its words checked as the reply's own;
(e) with `grounding`: a number or a link that no tool result (nor the person's message)
    holds: "ungrounded_fact:number", "ungrounded_url";
(f) with `qa` (the turn only searched and read the official pages): an answer that
    neither quotes a passage verbatim nor says the pages don't answer: "unquoted_answer".

It returns short reason codes, never the reply text ("eligibility_claim:validity" for
"your document is valid", an unknown id only when it is id-shaped), so nothing the
citizen wrote ends up in logs. The agent regenerates once with the reasons; if the
second reply is blocked too, the citizen gets a safe fallback with the official page.

    from onevisit import validator
    reasons = validator.check_reply(text, known_ids=..., read_ids=..., used_facts=True,
                                    official_texts=validator.official_texts_in_trace(trace),
                                    grounding=validator.grounding_in_trace(trace))
"""
from __future__ import annotations

import functools
import json
import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import urljoin

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

# "Your <document> is valid / sufficient / complete" in it, en, es, fr. The document may take up to four
# words, apostrophes and "di/de" included ("la tua carta d'identità", "tu tarjeta de identidad").
_NOUN = r"(?:[^\s.!?;]+\s+){0,3}?[^\s.!?;]+"
_VALIDITY_RES = (
    re.compile(r"\b(?:il tuo|la tua|i tuoi|le tue|tuo|tua|tuoi|tue)\s+" + _NOUN + r"\s+(?:e|sono|risulta|risultano)\s+"
               r"(?:valid[oaie]|sufficient[ei]|complet[oaie]|corrett[oaie])\b"),
    re.compile(r"\byour\s+" + _NOUN + r"\s+(?:is|are|looks|look)\s+(?:valid|sufficient|complete|correct|fine|enough)\b"),
    re.compile(r"\b(?:tu|tus)\s+" + _NOUN + r"\s+(?:es|son|esta|estan)\s+(?:valid[oa]s?|suficientes?|complet[oa]s?)\b"),
    re.compile(r"\b(?:ton|ta|tes|votre|vos)\s+" + _NOUN + r"\s+(?:est|sont)\s+(?:valides?|suffisante?s?|complete?s?)\b"),
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
    """Eligibility or validity claims in the text: the phrases of FORBIDDEN_PHRASES found (folded, in order
    of appearance), and "validity" for each "your <document> is valid" (a fixed code: the match would copy
    the person's words)."""
    folded = fold(text)
    found = [re.sub(r"\s+", " ", m.group(1)) for m in _FORBIDDEN_RE.finditer(folded)]
    found += ["validity" for r in _VALIDITY_RES for _ in r.finditer(folded)]
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


# Digits, amounts, times and links: facts, whatever the length of the reply.
_FACT_MARK = re.compile(r"\d|€|\bhttps?://|\bwww\.", re.IGNORECASE)
_CITATION_SPAN = re.compile(r"\[[^\[\]\n]{1,120}\](?!\()")
_SENTENCES = re.compile(r"(?<=[.!?;:。！？؟])\s+")
UNTOOLED_FACT_WORDS = 40  # a reply this long, with no tool at all this turn and no question at the end, states facts


def _own_text(text: str) -> str:
    """The reply without its citations ([cie], [ds549]): what the facts checks read."""
    return _CITATION_SPAN.sub(" ", text)


def _has_fact_marks(text: str) -> bool:
    return bool(_FACT_MARK.search(_own_text(text)))


def _has_passages(trace: list[dict]) -> bool:
    return any(isinstance(step.get("output"), dict) and (step["output"].get("results") or step["output"].get("passages"))
               for step in trace)


def _is_question_only(text: str, trace: list[dict] | None = None) -> bool:
    """A short reply that only asks the next question carries no facts to cite: at most 240 characters,
    ending with a question mark, no digits, amounts or links; after a search of the official pages (whose
    passages a reply could state as facts) only a single sentence."""
    stripped = text.strip()
    if len(stripped) > 240 or not stripped.endswith(("?", "؟", "？")) or _has_fact_marks(stripped):
        return False
    return not (trace and _has_passages(trace)) or len(_SENTENCES.split(stripped)) == 1


def used_facts(trace: list[dict], text: str) -> bool:
    """True when the reply presents facts that need a source: this turn's tools returned requirements,
    steps, offices or passages of the official pages and the reply is more than a short question; or,
    whatever the tools did, the reply has digits, amounts or links; or no tool ran this turn and the reply
    is a long statement (UNTOOLED_FACT_WORDS words, no question at the end): a fact from memory needs a
    source too."""
    if _is_question_only(text, trace):
        return False
    if _has_fact_marks(text):
        return True
    for step in trace:
        out = step.get("output")
        if isinstance(out, dict) and (out.get("requirements") or out.get("steps") or out.get("sections")
                                      or out.get("results") or out.get("passages")):
            return True
        if step.get("tool") == "find_offices" and isinstance(out, list) and out:
            return True
    stripped = text.strip()
    return (not trace and len(_own_text(stripped).split()) > UNTOOLED_FACT_WORDS
            and not stripped.endswith(("?", "؟", "？")))


# ---------- quotes of the official pages: « ... » (and “ ”, " ", „ “, 「」, 『』, ‹ ›, > lines) ----------
QUOTE_RE = re.compile(r"«([^«»]{1,3000})»")
# Other quotation marks: a span in them is checked like a « » quote when a citation follows it or it
# has OTHER_QUOTE_MIN_WORDS words (a Chinese reply quotes with 「」, an English one with “ ”).
_OTHER_QUOTES = (
    re.compile(r"„([^„“”«»\n]{1,1500})[“”]"),
    re.compile(r"“([^“”«»\n]{1,1500})”"),
    re.compile(r"「([^「」\n]{1,1500})」"),
    re.compile(r"『([^『』\n]{1,1500})』"),
    re.compile(r"‹([^‹›\n]{1,1500})›"),
    re.compile(r'(?<![\w"])"([^"\n«»]{1,1500})"'),
    re.compile(r"(?m)^[ \t]*>[ \t]?([^\n«»]+?)(?=\s*(?:\[[^\[\]\n]{1,120}\])?[ \t]*$)"),  # a Markdown blockquote line
)
OTHER_QUOTE_MIN_WORDS = 4
QUOTE_MARKS = "«»“”„「」『』‹›\""
# Right after a quote: its citation, e.g. «...» [cie-faq-00580] or «...», [cie].
_CITE_AFTER = re.compile(r"\s*[,.;:]?\s*\[([^\[\]\n]{1,120})\](?!\()")
_ELLIPSIS = re.compile(r"\s*(?:\[\s*(?:\.{3}|…)\s*\]|\(\s*(?:\.{3}|…)\s*\)|\.{3}|…)\s*")
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_LINE_MARK = re.compile(r"(?m)^[ \t]*(?:#{1,6}|[-*+>•]|\d+[.)])[ \t]+")
_INLINE_MARK = re.compile(r"(?:(?<=\s)|^)[-*+•](?:\s+|$)")  # a list copied onto one line: "documenti: - a; - b"
_CHARS = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201b": "'", "\u02bc": "'", "\u201c": '"', "\u201d": '"',
                        "\u201e": '"', "\u00ab": '"', "\u00bb": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " ",
                        "*": None, "`": None})
_EDGE = " \t\n.,;:!\"'-"  # not "?": a question quoted without its "?" reads as a statement
TERM_MAX_WORDS = 3  # «Procedi senza registrazione»: a name, not a sentence
# An ellipsis may skip words inside one paragraph: at most MAX_ELLIPSES, each part at least
# ELLIPSIS_PART_MIN_WORDS words (never a lone "non"), each gap at most MAX_ELLIPSIS_GAP characters.
MAX_ELLIPSES = 2
ELLIPSIS_PART_MIN_WORDS = 4
MAX_ELLIPSIS_GAP = 200
# A verified quote shelters its words from the eligibility check only when it is a sentence: this many
# words, or a whole sentence or line of the page of at least WHOLE_MIN_WORDS words.
EXEMPT_MIN_WORDS = 6
WHOLE_MIN_WORDS = 3


def normalize_quote(text: str) -> str:
    """Text as compared for quotes: Markdown links (their text kept; link targets are checked apart,
    see check_reply), list marks (at a line start or copied inline as " - "), emphasis, typographic
    quotes (guillemets inside a page's text too: a quote quotes them as “ ”), dashes, spacing and case
    don't count; letters, accents, digits and words do."""
    text = unicodedata.normalize("NFC", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _LINE_MARK.sub("", text).replace("__", "").translate(_CHARS)
    text = re.sub(r"\s+", " ", text).strip()
    return _INLINE_MARK.sub("", text).strip().casefold()


class _Hay:
    """A source text normalized for quotes, with the offsets where its lines and paragraphs start."""

    __slots__ = ("text", "lines", "paragraphs")

    def __init__(self, body: str) -> None:
        parts: list[str] = []
        self.lines: list[int] = []
        self.paragraphs: list[int] = []
        at, new_paragraph = 0, True
        for line in body.split("\n"):
            norm = normalize_quote(line)
            if not norm:
                new_paragraph = True
                continue
            if parts:
                at += 1  # the joining space
            self.lines.append(at)
            if new_paragraph:
                self.paragraphs.append(at)
            parts.append(norm)
            at += len(norm)
            new_paragraph = False
        self.text = " ".join(parts)

    def boundary_before(self, i: int) -> bool:
        """A sentence or a line starts at i."""
        if i == 0 or i in self.lines:
            return True
        before = self.text[:i].rstrip()
        return before.endswith((".", "!", "?", ";", ":"))

    def boundary_after(self, j: int) -> bool:
        """A sentence or a line ends at j."""
        if j >= len(self.text) or (j + 1) in self.lines:
            return True
        return self.text[j:j + 1] in (".", "!", "?", ";", ":") or self.text[j:].lstrip()[:1] in (".", "!", "?", ";")


@functools.lru_cache(maxsize=2048)
def _hay(body: str) -> _Hay:
    return _Hay(body)


def _word_edge(text: str, i: int) -> bool:
    """No letter or digit on both sides of position i (a quote never starts or ends inside a word)."""
    return not (0 < i < len(text) and text[i - 1].isalnum() and text[i].isalnum())


def _occurrences(hay: _Hay, fragment: str, at: int, until: int) -> list[int]:
    """Where a fragment occurs in the text, from `at`, starting before `until`, on word boundaries; a
    fragment that stops where the page has a question mark is not a match (it turns a question into a
    statement)."""
    out = []
    text = hay.text
    found = text.find(fragment, at)
    while 0 <= found < until:
        end = found + len(fragment)
        question_cut = not fragment.endswith("?") and text[end:].lstrip()[:1] == "?"
        if _word_edge(text, found) and _word_edge(text, end) and not question_cut:
            out.append(found)
        found = text.find(fragment, found + 1)
    return out


def _match(hay: _Hay, fragments: list[str]) -> tuple[int, int] | None:
    """The span of the first match of every fragment, in order, each next one within MAX_ELLIPSIS_GAP
    characters of the one before and in the same paragraph; None when there is none."""
    for first in _occurrences(hay, fragments[0], 0, len(hay.text) + 1):
        end = first + len(fragments[0])
        if len(fragments) == 1:
            return first, end
        paragraph_end = next((p for p in hay.paragraphs if p > end), len(hay.text) + 1)
        last = _match_rest(hay, fragments, 1, end, paragraph_end)
        if last is not None:
            return first, last
    return None


def _match_rest(hay: _Hay, fragments: list[str], k: int, at: int, paragraph_end: int) -> int | None:
    for start in _occurrences(hay, fragments[k], at, min(at + MAX_ELLIPSIS_GAP + 1, paragraph_end)):
        end = start + len(fragments[k])
        if k == len(fragments) - 1:
            return end
        found = _match_rest(hay, fragments, k + 1, end, paragraph_end)
        if found is not None:
            return found
    return None


def official_texts(obj: object, source_id: str | None = None) -> list[tuple[str, str]]:
    """(source_id, verbatim text) pairs inside a tool result: the passages of
    search_official_pages and read_source (text and heading, each with the source of its
    page) and the verbatim `quote` of checklist items, steps and form sections. OneVisit's
    own wording (text_it, text_en, labels) is not official text and is left out."""
    found: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        if isinstance(obj.get("source_id"), str):
            source_id = obj["source_id"]
        if source_id:
            if isinstance(obj.get("quote"), str) and obj["quote"].strip():
                found.append((source_id, obj["quote"]))
            if "passage_id" in obj:
                found += [(source_id, obj[k]) for k in ("text", "heading") if isinstance(obj.get(k), str) and obj[k]]
        for value in obj.values():
            found += official_texts(value, source_id)
    elif isinstance(obj, list):
        for value in obj:
            found += official_texts(value, source_id)
    return found


def official_texts_in_trace(trace: list[dict]) -> list[tuple[str, str]]:
    """Official text returned by the tool calls of one turn."""
    return [pair for step in trace for pair in official_texts(step.get("output"))]


def _tool_results(messages: list) -> list[object]:
    """The decoded tool_result contents of an API history."""
    out: list[object] = []
    for m in messages:
        content = m.get("content") if isinstance(m, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                raw = block.get("content")
                try:
                    out.append(json.loads(raw) if isinstance(raw, str) else raw)
                except (TypeError, ValueError):
                    continue
    return out


def official_texts_in_messages(messages: list) -> list[tuple[str, str]]:
    """Official text returned by tools earlier in the API history (tool_result blocks)."""
    return [pair for result in _tool_results(messages) for pair in official_texts(result)]


# ---------- grounding: the numbers and links of a reply come from the tools (or the person's words) ----------
_NUMBER = re.compile(r"(?<![A-Za-z0-9_\-#/])\d+(?:[.,:]\d+)*")
_URL = re.compile(r"https?://[^\s<>()\[\]\"'«»“”]+", re.IGNORECASE)
_LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
_LIST_NUMBER = re.compile(r"(?m)^[ \t]*\d+[.)][ \t]+")


def grounding_strings(obj: object) -> list[str]:
    """Every string inside a tool result, and the links of its passages made absolute against the page
    URL ("/servizi" on comune.milano.it): what a reply's numbers and links may come from. Ids are
    left out (their digits are no fact)."""
    out: list[str] = []
    if isinstance(obj, dict):
        base = obj.get("url") if isinstance(obj.get("url"), str) else ""
        for key, value in obj.items():
            if key in ("id", "source_id", "passage_id", "source_ids", "office_id"):
                continue
            if isinstance(value, str):
                out.append(value)
                if base and key == "text":
                    out += [urljoin(base, t) for t in _LINK_TARGET.findall(value)]
            else:
                out += grounding_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            out += grounding_strings(value)
    elif isinstance(obj, str):
        out.append(obj)
    return out


def grounding_in_trace(trace: list[dict]) -> list[str]:
    """The strings this turn's tools returned (see grounding_strings)."""
    return [s for step in trace for s in grounding_strings(step.get("output"))]


def grounding_in_messages(messages: list) -> list[str]:
    """The strings tools returned earlier in the API history, and what the person wrote."""
    out = [s for result in _tool_results(messages) for s in grounding_strings(result)]
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
            out.append(m["content"])
    return out


def _number_key(token: str) -> str:
    return ".".join(part.lstrip("0") or "0" for part in re.split(r"[.,:]", token))


def _numbers_allowed(strings: Iterable[str]) -> set[str]:
    allowed: set[str] = set()
    for s in strings:
        for token in _NUMBER.findall(_URL.sub(" ", s)):
            parts = [p.lstrip("0") or "0" for p in re.split(r"[.,:]", token)]
            allowed.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
            allowed.update(parts)
    return allowed


def _url_key(url: str) -> str:
    url = url.rstrip(".,;:!?)").split("#", 1)[0]
    scheme, _, rest = url.partition("://")
    host, slash, path = rest.partition("/")
    return f"{scheme.lower()}://{host.lower()}{slash}{path}".rstrip("/")


def ungrounded(text: str, strings: Iterable[str]) -> list[str]:
    """Reason codes for the numbers ("ungrounded_fact:number") and links ("ungrounded_url") of a reply
    that no tool result of the conversation (nor the person's own words) holds: a fee, an age, a day
    count or a booking link from memory, or one placed by an instruction hidden in a page."""
    strings = list(strings)
    reasons = []
    urls = {_url_key(u) for s in strings for u in _URL.findall(s)}
    if any(_url_key(u) not in urls for u in _URL.findall(text)):
        reasons.append("ungrounded_url")
    own = _LIST_NUMBER.sub(" ", _URL.sub(" ", _own_text(text)))
    allowed = _numbers_allowed(strings)
    if any(_number_key(t) not in allowed for t in _NUMBER.findall(own)):
        reasons.append("ungrounded_fact:number")
    return reasons


# ---------- don't-know replies ----------
# The reply says that the saved official pages don't answer. Folded (lower case, no accents); the Spanish
# "no sé" is matched before folding (folded, it is the reflexive "no se puede").
DONT_KNOW: dict[str, tuple[str, ...]] = {
    "it": ("non lo dic", "non dicono", "non indica", "non specifica", "non riporta", "non trovo", "non ho trovato",
           "non so ", "non lo so", "non ho informazion", "non contengono", "non spiega", "non risulta",
           "nessuna informazion", "non parla", "non menziona", "non descriv", "non precisa", "non ne parla",
           "non c'e una risposta", "non trattano", "non coprono", "non ho una fonte", "non ho fonti"),
    "en": ("don't say", "do not say", "doesn't say", "does not say", "don't mention", "do not mention",
           "doesn't mention", "does not mention", "don't know", "do not know", "no information",
           "not covered", "don't cover", "do not cover", "doesn't cover", "does not cover", "couldn't find",
           "could not find", "can't find", "cannot find", "don't explain", "do not explain", "don't specify",
           "do not specify", "not stated", "nothing about", "no saved", "don't have a verified",
           "don't have a source", "not say"),
    "es": ("no lo dic", "no dicen", "no indica", "no menciona", "no lo se", "no se si", "no encuentro",
           "no he encontrado", "no hay informacion", "no explica", "no especifica", "no tengo una fuente",
           "no contienen", "no cubren", "no aparece"),
    "fr": ("ne disent pas", "ne le disent pas", "ne mentionnent pas", "ne precisent pas", "je ne sais pas",
           "pas d'information", "n'indiquent pas", "n'expliquent pas", "ne trouve pas", "n'ai pas trouve",
           "ne couvrent pas", "ne contiennent pas"),
    "pt": ("nao dizem", "nao sei", "nao encontrei", "nao mencionam", "nao ha informacao"),
    "ar": ("لا تذكر", "لا تقول", "لا اعرف", "لم اجد", "لا توجد معلومات", "لا تتضمن", "لا تحدد", "لا توضح",
           "لا تشير", "ليس لدي مصدر", "لا تغطي"),
    "zh": ("没有提到", "没有说明", "没有说", "未提及", "未说明", "不知道", "没有找到", "没有相关信息", "没有信息",
           "并未", "没有涉及", "未涉及"),
    "uk": ("не вказано", "не вказують", "не згадують", "не знаю", "немає інформації", "не містять", "не кажуть",
           "не пояснюють", "не знайш", "не зазначено"),
    "bn": ("জানি না", "উল্লেখ নেই", "বলা নেই", "তথ্য নেই", "উল্লেখ করা হয়নি", "পাওয়া যায়নি", "বলে না"),
}
_DONT_KNOW_RAW = re.compile(r"(?<!\w)no sé(?!\w)", re.IGNORECASE)


@functools.lru_cache(maxsize=1)
def _dont_know_folded() -> tuple[str, ...]:
    return tuple(dict.fromkeys(fold(p) for ps in DONT_KNOW.values() for p in ps))


def says_dont_know(text: str) -> bool:
    """The reply says the saved official pages don't answer (any language of DONT_KNOW)."""
    if _DONT_KNOW_RAW.search(text or ""):
        return True
    folded = fold(text or "")
    return any(p in folded for p in _dont_know_folded())


def quote_spans(text: str) -> list[tuple[int, int, str, str]]:
    """The quotes of a reply as (start, end, inner text, opening mark), in order: every « » quote, and a
    span in other quotation marks (“ ”, " ", „ “, 「」, 『』, ‹ ›) or a Markdown '>' line when a citation
    follows it or it has OTHER_QUOTE_MIN_WORDS words or more (shorter, uncited: a name, not a quote)."""
    spans = [(m.start(), m.end(), m.group(1), "«") for m in QUOTE_RE.finditer(text)]
    for pattern in _OTHER_QUOTES:
        for m in pattern.finditer(text):
            start, end = m.start(), m.end()
            if any(a < end and start < b for a, b, _, _ in spans):
                continue
            inner = m.group(1).strip()
            cited = bool(_CITE_AFTER.match(text, end))
            if inner and (cited or len(inner.split()) >= OTHER_QUOTE_MIN_WORDS
                          or (_CJK.search(inner) and len(inner) >= 2 * OTHER_QUOTE_MIN_WORDS)):
                spans.append((start, end, m.group(1), text[start:m.start(1)].strip() or ">"))
    return sorted(spans)


def _fragments(quote: str) -> list[str]:
    parts = (normalize_quote(p).strip(_EDGE) for p in _ELLIPSIS.split(quote))
    return [p for p in parts if p]


def verify_quotes(text: str, texts: Iterable[tuple[str, str]], known_ids: Iterable[str] = ()) -> list[dict]:
    """Every quote of the reply (see quote_spans) and what the official texts say about it.

    Each: {"n" (1-based), "start", "end" (the span with its marks), "text" (as written), "status",
    "source_ids" (sources whose text holds it), "cited" (ids in the citation right after it), "exact"
    (one verbatim piece, no ellipsis), "exempt" (a verified sentence: its words are the page's, not
    checked for eligibility words)}. status: "verified" (a verbatim slice of official text, on word
    boundaries, of a cited source when a citation follows; "…" may skip words inside one paragraph, at
    most MAX_ELLIPSES times, each part ELLIPSIS_PART_MIN_WORDS words or more), "mismatch" (verbatim, but
    of another source than the one cited), "term" (three words or fewer, no digits, no citation after
    it, not found: a name, not checked) or "invented".
    """
    hays: dict[str, list[_Hay]] = {}
    for sid, body in texts:
        hays.setdefault(sid, []).append(_hay(body))
    known = set(known_ids)
    out = []
    for n, (start, end, inner, mark) in enumerate(quote_spans(text), start=1):
        after = _CITE_AFTER.match(text, end)
        cited = cited_source_ids(f"[{after.group(1)}]", known) if after else []
        fragments = _fragments(inner)
        usable = bool(fragments) and len(fragments) <= MAX_ELLIPSES + 1 and (
            len(fragments) == 1 or all(len(f.split()) >= ELLIPSIS_PART_MIN_WORDS for f in fragments))
        holders, whole = [], False
        if usable:
            for sid, bodies in hays.items():
                for hay in bodies:
                    span = _match(hay, fragments)
                    if span:
                        if sid not in holders:
                            holders.append(sid)
                        whole = whole or (hay.boundary_before(span[0]) and hay.boundary_after(span[1]))
        words = len(" ".join(fragments).split())
        if holders and (not cited or set(cited) & set(holders)):
            status = "verified"
        elif holders:
            status = "mismatch"
        elif not cited and not re.search(r"\d", inner) and words <= TERM_MAX_WORDS:
            status = "term"
        else:
            status = "invented"
        exact = len(fragments) == 1
        exempt = status == "verified" and exact and (words >= EXEMPT_MIN_WORDS or (whole and words >= WHOLE_MIN_WORDS))
        out.append({"n": n, "start": start, "end": end, "text": inner.strip(), "status": status,
                    "source_ids": holders, "cited": cited, "exact": exact, "exempt": exempt, "mark": mark})
    return out


_STRIP_MARKS = str.maketrans({c: " " for c in QUOTE_MARKS + "*_`>"})


def _validity_across_quotes(text: str, quotes: list[dict]) -> bool:
    """A "your <document> is valid" that starts in the reply's own words and ends inside a verified quote
    ("La tua carta: «la Carta d'identità è valida»"): the quote's words are the page's, the claim is not."""
    pieces: list[tuple[str, bool]] = []
    at = 0
    for q in quotes:
        if not q["exempt"]:
            continue
        pieces.append((text[at:q["start"]], False))
        pieces.append((text[q["start"]:q["end"]], True))
        at = q["end"]
    if not any(inside for _, inside in pieces):
        return False
    pieces.append((text[at:], False))
    folded, inside_at = "", []
    for piece, inside in pieces:
        part = fold(piece.translate(_STRIP_MARKS))
        if inside:
            inside_at.append((len(folded), len(folded) + len(part)))
        folded += part
    for pattern in _VALIDITY_RES:
        for m in pattern.finditer(folded):
            overlaps = [(a, b) for a, b in inside_at if a < m.end() and m.start() < b]
            if overlaps and not any(a <= m.start() and m.end() <= b for a, b in overlaps):
                return True
    return False


def check_reply(text: str, *, known_ids: Iterable[str], read_ids: Iterable[str], used_facts: bool,
                official_texts: Iterable[tuple[str, str]] | None = None,
                grounding: Iterable[str] | None = None, qa: bool = False) -> list[str]:
    """Reasons to block the reply; an empty list means it can reach the citizen.

    With `official_texts` (the (source_id, text) pairs the tools returned in this conversation:
    official_texts_in_trace + official_texts_in_messages), every quote is checked (see verify_quotes)
    and the eligibility words are looked for outside the verified quotes that are sentences (a one-word
    «idonea» is the reply's own word). Without it (older callers) quotes are not checked and the whole
    reply is searched for eligibility words. With `grounding` (the strings the tools returned and what
    the person wrote: grounding_in_trace + grounding_in_messages), every number and link must be in it
    ("ungrounded_fact:number", "ungrounded_url"). `qa`: the turn only searched and read the official
    pages (no checklist, no offices): a reply that states facts must quote a passage verbatim or say the
    pages don't answer ("unquoted_answer").
    """
    known, read = set(known_ids), set(read_ids)
    reasons: list[str] = []
    cited = cited_source_ids(text, known)
    for sid in cited:
        if sid not in known:
            reasons.append(f"unknown_source:{sid}" if len(sid) <= 40 else "unknown_source")
        elif sid not in read:
            reasons.append(f"source_not_read:{sid}")
    own_words = text
    quotes: list[dict] = []
    if official_texts is not None:
        quotes = verify_quotes(text, official_texts, known)
        for q in quotes:
            if q["status"] == "invented":
                reasons.append(f"invented_quote:{q['n']}")
            elif q["status"] == "mismatch":
                reasons += [f"quote_source_mismatch:{sid}" for sid in q["cited"]]
        own_words = _without(text, [(q["start"], q["end"]) for q in quotes if q["exempt"]])
        if _validity_across_quotes(text, quotes):
            reasons.append("eligibility_claim:validity")
    own_words = own_words.translate(_STRIP_MARKS)  # «è valido», “all set”: the marks don't hide the words
    reasons += [f"eligibility_claim:{p}" for p in dict.fromkeys(forbidden_phrases_in(own_words))]
    if used_facts and not cited:
        reasons.append("missing_citation")
    if grounding is not None:
        reasons += ungrounded(text, grounding)
    if qa and used_facts and not any(q["status"] == "verified" for q in quotes) and not says_dont_know(text):
        reasons.append("unquoted_answer")
    return list(dict.fromkeys(reasons))


def _without(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + " " + text[end:]
    return text


_DESCRIBE = {
    "it": {"unknown_source": "fonte inesistente", "source_not_read": "fonte non letta in questa conversazione",
           "eligibility_claim": "parola che promette l'esito", "missing_citation": "fatti senza fonte",
           "invented_quote": "citazione che non è nelle pagine lette",
           "quote_source_mismatch": "citazione attribuita alla fonte sbagliata",
           "ungrounded_fact": "numero che nessuno strumento ha restituito",
           "ungrounded_url": "link che nessuno strumento ha restituito",
           "unquoted_answer": "risposta senza citazione né «le pagine non lo dicono»"},
    "en": {"unknown_source": "unknown source", "source_not_read": "source not read in this conversation",
           "eligibility_claim": "word that promises the outcome", "missing_citation": "facts without a source",
           "invented_quote": "quote not found in the pages read",
           "quote_source_mismatch": "quote attributed to the wrong source",
           "ungrounded_fact": "number no tool returned",
           "ungrounded_url": "link no tool returned",
           "unquoted_answer": "answer with no quote and no \"the pages don't say\""},
}


def describe(reasons: list[str], lang: str = "en") -> str:
    """Short human-readable summary of the reasons (Italian or English)."""
    labels = _DESCRIBE.get(lang, _DESCRIBE["en"])
    parts = []
    for r in reasons:
        code, _, detail = r.partition(":")
        label = labels.get(code, code)
        if code in ("invented_quote", "ungrounded_fact") or detail == "validity":
            detail = ""  # the quote's number, the kind of fact: nothing to the reader
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
        "text between « » must be copied exactly from a passage or quote a tool returned in this conversation, "
        "in the page's own language, followed by the source id of that page (never put a translation or your own "
        "words between « », “ ”, 「」 or any other quotation marks: they are all checked); an ellipsis may skip words "
        "only inside one paragraph, never a 'non'; "
        "every number, amount, time, age, day count and link you write must appear in a tool result of this "
        "conversation (don't count items, don't compute); "
        "when you answer a question from the official pages, quote the deciding sentence verbatim; "
        "if no passage answers, say that the saved official pages don't say it and give the "
        "official page with its source id; "
        "never say or imply that the person or their documents are eligible, valid, complete, in order, "
        "accepted or guaranteed, not even in a negative sentence: say that the officer at the desk decides. "
        "Do not mention this check."
    )
