"""Passage search over the saved official pages (data/pages/*.md). Standard library only.

The agent answers an open question ("can my son travel with the receipt?", "¿cuánto cuesta
el DNI?") only from what the official pages say. This module finds the passages to quote:

    from onevisit import search
    search.search("I lost my ID card", service_id="carta-identita", k=5)
    -> [{"source_id": "cie-faq-00580", "title": ..., "publisher": "Comune di Milano",
         "url": ..., "saved_at": "2026-10-04", "updated_at": "2025-12-01", "kind": "faq",
         "heading": "Ho perso la ...?", "text": "<verbatim passage of the saved page>",
         "score": 9.87, "confidence": 0.93, "confident": True, ...}, ...]
    search.best_answer("Posso pagare con Satispay?", service_id="carta-identita")
    -> {"confident": ..., "confidence": ..., "reason": "ok" | "no_match" | "weak_match" |
        "other_document" | "unknown_words", "passages": [...]}

How it works:

- Every page in data/pages/*.md (front matter + Markdown body, written by `onevisit ingest`)
  is cut into passages: by Markdown heading, then by paragraph and list block, ~40-220 words.
  A passage's `text` is always a verbatim slice of the page body; menus, breadcrumbs,
  share buttons and image-only blocks are left out, never rewritten.
- A question heading (every heading of a support-centre FAQ page, any heading that ends
  with "?") stays with its answer in one passage, and the question's words count three times.
  A tab label the City's pages put one level above its section ("### Carta d'identità
  provvisoria", then "## Documenti da presentare") stays inside that section
  (_heading_levels): the provisional card's list is not the CIE's.
- Ranking is BM25 over words without accents, lower-case, without stopwords (Italian,
  English, Spanish, French, and the city's name: every page is about Milan), lightly stemmed
  ("documenti", "documentos", "documents" -> "document"; "-zione", "-ción" -> "-tion").
  Concepts from onevisit/search_synonyms.json ("lost": perso, smarrimento, lost, perdido,
  perdu, مفقود, 丢失, загубила, হারিয়ে ...) become one shared term, so a question in English,
  Spanish, French, Arabic, Chinese, Ukrainian or Bengali finds the Italian passage; the words
  of a concept phrase then only break ties. A concept's IDF is over all passages; a word
  found only in the few English pages gets its IDF among those pages and counts half, so
  English questions are not pulled to the English guides. Arabic, Cyrillic and Bengali
  phrases match at the start of a word, short ones as the whole word ("وجه", face, is not
  in "أتوجه", I go); a concept's 'not' phrases ("ho subito un furto", "I arrived in Milan")
  stop a match. Numbers weigh half, and the numbers of identifiers ("circolare n.81/2023")
  are not read.
- Query words: chat shorthand is read as the word ("nn" -> "non", "u" -> "you"), and a word
  that no page and no concept knows is read as the known word one typing error away
  ("expierd" -> "expired", "documneti" -> "documenti", same first letter, 6+ letters), never
  a verb form with one letter changed ("votare" stays "votare", not "volare") nor a word
  the pages hardly use. A message with two questions ("quanto costa e quali documenti
  servono?") is searched one question at a time, the results alternating.
- Then: a passage with only some of the concepts asked loses a little (coordination); a
  section whose heading is about something not asked loses more ("I lost my ID card" is not
  "I lost my PIN"), except for a concept the heading names together with the one asked
  ("Furto e smarrimento"); question words ("how many", "what is") weigh less and are never a
  topic; FAQ answers win ties, YesMilano guides and news lose them (the City's and the
  Ministry's own pages first), the Ministry's circulars to registry staff lose more, and old
  news and circulars more still (the page's own date, `updated_at`); for what the City sets
  itself (its fee, offices, hours, booking) its own pages come first; a page that repeats a
  section gives it once.
- Confidence: each result says how much of the question it holds (`confidence`: its score,
  at most HELD_FACTOR times the IDF of the query terms it holds, against what a passage
  holding every query word once would score, a word no page has counting as the rarest and
  a word of another script that no concept reads as half of one) and whether it looks like
  an answer (`confident`: confidence 0.4, a score of at least MIN_SCORE). A question about
  another document than the service's own (renewing a passport, getting SPID; bringing one
  to the appointment is about this service), one that asks only what every page is about
  ("carta?") or whose words are mostly unknown is never confident. Lexical matching can't
  tell a page on the same topic from a page that answers: about half of the bank's
  unanswerable questions still come out confident, so Claude must read the passage before
  quoting it.
- The index is built at first use (~0.6 s for ~130 pages) and rebuilt whenever a file in
  data/pages, data/sources.csv or the synonym file changes (names, sizes, mtimes): a page
  added by the crawler is searchable on the next query, no restart needed.

Nothing here states a fact: the passages are the City's, the Ministry's or YesMilano's own
words, with the page and the date it was saved. When nothing matches, the result is empty
and the agent must say it doesn't know and link the official page.

    python -m onevisit.search "how much does the ID card cost" --service carta-identita
    python -m onevisit.search --stats
    python -m onevisit.search "posso pagare con satispay" --service carta-identita --best
    python -m onevisit.search --eval data/eval/qa/search-retrieval.json
    python data/eval/qa/run_retrieval.py      # hit@1/3/5 on the ID card question bank
"""

from __future__ import annotations

import contextlib
import csv
import datetime
import fnmatch
import functools
import hashlib
import json
import math
import pathlib
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"
SYNONYMS_FILE = pathlib.Path(__file__).resolve().with_name("search_synonyms.json")

# Passage size, in words (link text counts, link targets don't).
MIN_WORDS = 40
MAX_WORDS = 220
HARD_MAX_WORDS = 286  # a passage under MIN_WORDS may grow this far rather than stay tiny
FAQ_MAX_WORDS = 600  # a question and its answer stay together up to this size

# BM25 and field weights.
K1 = 1.2
B = 0.75
LENGTH_FLOOR = 25  # a 3-word passage is normalised as if it had 25 words
QUESTION_WEIGHT = 3.0  # the question of a question heading
HEADING_WEIGHT = 2.0  # the passage's own heading
PARENT_HEADING_WEIGHT = 0.5  # the headings above it
TITLE_WEIGHT = 0.5  # the page title (not for FAQ pages, whose title is the question)
LANG_BOOST = 1.1  # passages written in the `lang` asked for
COVERED_WEIGHT = 0.3  # a word that is part of a concept phrase ("lost", "via larga")
COORDINATION = 0.4  # with 2+ concepts asked, a passage with half of them loses 20%
EXTRA_TOPIC_PENALTY = 0.85  # per concept in a passage's own heading the query didn't ask about
DISTINCT_TOPIC_PENALTY = 0.7  # ... when that concept is another object ("distinct": PIN codes)
EXTRA_TOPIC_FLOOR = 0.6
ONE_LANGUAGE_SHARE = 0.9  # a word found (almost) only in English pages gets its IDF among them
MINORITY_LANGUAGE_WEIGHT = 0.5  # ... and counts half in a query: the Italian pages can't match it
MINORITY_SHARE = 0.3  # a language with fewer passages than this is a minority (English here)
KIND_PRIOR = {"faq": 1.1, "page": 1.0, "form": 1.0, "pdf": 0.95, "news": 0.85, "circular": 0.8}
# Kinds sources.csv can't tell: the Ministry's circulars are PDFs written for prefectures and
# registry staff (toner, workstations, protocol numbers), not for citizens.
KIND_BY_ID = (("circ-*", "circular"),)
# A page of these kinds older than the given days (counted back from the newest page's save
# date, so the same pages always rank the same) loses the given factor more: news announced
# in January may have been replaced since (the City's page says what holds), and a circular's
# office instructions date (the 2017 one on toner and workstations).
STALE = {"news": (180, 0.8), "circular": (5 * 365, 0.75)}
# What the City sets itself (its fee, its offices and hours, its booking): its own pages
# first, before the Ministry's national figures (EUR 16.79 is the State's share only).
LOCAL_PUBLISHER = "Comune di Milano"
LOCAL_CONCEPTS = frozenset({"§cost", "§hours", "§office", "§booking"})
LOCAL_BOOST = 1.15
# Guides written for newcomers by others than the office that applies the rule.
PUBLISHER_PRIOR = {"YesMilano": 0.9}
PER_SOURCE = 2  # at most this many passages of one page in a result
SPELL_MIN_WORD = 6  # shorter words are never corrected: "both" is not "booth", "treno" not "trento"
SPELL_CONCEPT_MIN_WORD = 7  # a correction that makes a concept word needs this many letters
SPELL_MIN_COUNT = 3  # ... any other correction, a word found this many times in the pages
# Verb and participle endings: such a word is a real form the pages don't use, not a typo of
# a word one letter away ("votare" is not "volare", "avuto" is not "aiuto").
_INFLECTIONS = ("are", "ere", "ire", "ato", "uto", "ito", "ing", "ed")

# Confidence: does a passage look like an answer, or only like the same topic? A result is
# "confident" when its score reaches MIN_RELATIVE of what a passage holding every query term
# once would score (_attainable: a word no page has counts as the rarest word, a word of
# another script that no concept reads as half of one), it scores MIN_SCORE and within
# RELATIVE_TO_TOP of the best result, and the query passes the gates in _gate(). With
# HELD_FACTOR, these keep 98% of the answerable tuning questions of data/eval/qa confident
# (data/eval/qa/run_retrieval.py); lexical scores can't do much better: see docs/knowledge.md.
MIN_RELATIVE = 0.40
# ... and a passage's score counts at most HELD_FACTOR times the IDF of the query terms it
# holds (each once): a section that repeats "foto" in its heading and text holds one word of
# "posso avere la barba nella foto?", not the whole question.
HELD_FACTOR = 1.6
RELATIVE_TO_TOP = 0.5
MAX_UNKNOWN_SHARE = 0.5  # more of the query's words than this unknown to every saved page
# A confident result scores at least this much, whatever the question asks: below it a
# passage shares a word or two with the question ("x x x x x carta"). The lowest top score of
# an answerable tuning question of data/eval/qa is about 1.7.
MIN_SCORE = 1.5
SCRIPT_GAP_WEIGHT = 0.25  # an Arabic/Chinese/Cyrillic/Bengali word no concept reads, as unseen
# Concepts that make another document something to bring, not the question's subject.
BRING_CONCEPTS = frozenset({"§documents", "§mandatory"})
# The thing a service is about: a question naming another document (a passport, a driving
# licence, SPID) and not this one is out of the service, whatever the passages share with it.
SERVICE_SUBJECT = {"carta-identita": "idcard"}

# Pages that belong to a service besides the ones its catalog cites (fnmatch patterns on ids).
SERVICE_PAGES = {
    "carta-identita": (
        "cie",
        "cie-*",
        "circ-dait-*",
        "prenotazione",
        "sedi-anagrafiche",
        "yesmilano-id-card",
        "yesmilano-work-identity-card",
        "news-cie-*",
        "news-cabine-foto-cie",
        "pds-denunce-online",
        "pds-espatrio-minori",
        "oggetti-smarriti",
        "news-anagrafe-*",
        "detenuti-direttive-news",
    ),
    "iscrizione-anagrafica-extra-ue": (
        "residenza-estero*",
        "permesso-soggiorno*",
        "codice-fiscale",
        "dimora-abituale",
        "rettifica-dati-stranieri",
        "yesmilano-students",
        "yesmilano-permesso",
        "yesmilano-codice-fiscale",
        "yesmilano-first-steps",
        "yesmilano-work-registering-resident",
    ),
    "cambio-residenza": ("cambio-residenza", "anpr-cambio-residenza"),
}

_STOP_IT = """
a ad al allo ai agli all agl alla alle con col coi da dal dallo dai dagli dall dagl dalla dalle di
del dello dei degli dell degl della delle in nel nello nei negli nell negl nella nelle su sul sullo
sui sugli sull sugl sulla sulle per tra fra il lo la i gli le l un uno una ed e o od ma se che chi
cui non come dove quando quale quali quanto quanta quanti quante questo questa questi queste quello
quella quelli quelle è sono sei siamo siete ho hai ha abbiamo avete hanno essere avere mi ti ci vi
si ne mio mia miei mie tuo tua tuoi tue suo sua suoi sue loro nostro nostra vostro vostra io tu
lui lei noi voi anche più molto già solo così ogni tutto tutti tutte posso puoi può possono devo
deve devono fare fa faccio stato stata sia sarà viene vengono c d s m t po essa esso nostri
cosa
"""
_STOP_EN = """
a an the and or but if of to in on at by for with from as is are was were be been being am do
does did doing have has had i me my mine you your yours he him his she her it its we us our they
them their this that these those what which who whom whose how when where why can could should
would will shall may might must not no so than too very just about into out up there here any
some all also get got need want s t don many much go goes going come take takes make please tell
know someone something anything thing like would im ive dont cant
"""
_STOP_OTHER = """
el los las del al un una unos unas y o de en que por para con mi mis tu es son como qué cómo le
les des du et ou est sont pour avec mon ma mes je j il elle nous vous comment quoi une ce cette
doit dois avoir être faire peut peux puis puedo puede pueden tengo tiene hay hacer ser estar
soy ya dos algo hago necesito día dia ahora mucho suis faut fait fais veux adesso dice dico
voglio vorrei detto sapere succede mancano say says said doesn didn isn
never anymore myself yourself usual usually really still already
milano milan milán milanese
"""  # every page is about Milan: the city's name says nothing about a question's topic
# Numbers weigh less than words ("81" in a question is rarely its topic), and the numbers of
# identifiers are not read at all: "circolare n.81/2023", "prot. N.0017063" say nothing.
NUMBER_WEIGHT = 0.5
_IDENTIFIER = re.compile(r"\b(?:n|nr|no|num|prot)\s?[.°]\s?\d+(?:\s?/\s?\d+)*")
_IT_MARKERS = frozenset(
    {"il", "di", "che", "per", "non", "della", "sono", "del", "una", "con", "gli", "delle", "nel"}
)
_EN_MARKERS = frozenset(
    {"the", "and", "of", "to", "you", "your", "is", "are", "for", "with", "can", "will"}
)
# Digits apart ("12岁" is 12 + 岁). Indic vowel signs and viramas are marks, not letters, for
# Python's \w: without the second class "আইডি" (Bengali "ID") would split into pieces.
_WORD = re.compile(r"\d+|(?:[^\W\d_]|[\u0900-\u0dff])+")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BARE_URL = re.compile(r"<?(?:https?://|mailto:|tel:)\S+>?")
_LIST_MARK = r"(?:[-*+]|\d+[.)])?\s*"
_LINK_ONLY = re.compile(r"^\s*" + _LIST_MARK + r"(?:!?\[[^\]]*\]\([^)]*\)[\s/|·\-]*)+$")
_IMAGE_ONLY = re.compile(r"^\s*" + _LIST_MARK + r"(?:!\[[^\]]*\]\([^)]*\)\s*)+$")
_SENTENCE_END = re.compile(r"(?<=[.;:!?])\s+")
_NON_LATIN = re.compile(r"[^\x00-\u024f]")
_BOILERPLATE = frozenset(
    {
        "/",
        "...attendere prego...",
        "condividi",
        "contacts",
        "estensione - dimensione",
        "gallery",
        "leggi di più",
        "next",
        "prev",
        "share",
        "torna su",
        "video",
    }
)
_LIST_PREFIX = re.compile(r"^(?:[-*+]|\d+[.)])\s*")


# Marks dropped when folding: Latin, Greek and Cyrillic accents (U+0300-036F), Arabic vowel
# signs and hamza (U+064B-065F, U+0670). Other scripts' marks are part of the letter (Bengali).
_DROPPED_MARK = re.compile(r"[\u0300-\u036f\u064b-\u065f\u0670]")


def _fold(text: str) -> str:
    """Lower case without accents (Arabic diacritics and hamza forms included)."""
    return _DROPPED_MARK.sub("", unicodedata.normalize("NFKD", text)).casefold()


_STOPWORDS = frozenset(_fold(w) for w in (_STOP_IT + _STOP_EN + _STOP_OTHER).split())


def _plain(text: str) -> str:
    """Markdown text as read: images and link targets removed, link text kept."""
    text = _MD_IMAGE.sub(" ", text)
    text = _MD_LINK.sub(r" \1 ", text)
    return _BARE_URL.sub(" ", text)


def _words(text: str) -> list[str]:
    """Folded words of a Markdown text (no stemming, stopwords kept)."""
    return _WORD.findall(_fold(_plain(text)))


def _stem(word: str) -> str:
    """Light Italian/English/Spanish suffix stripping; the same rules for pages and queries."""
    if len(word) <= 3 or not word.isascii() or not word.isalpha():
        return word
    for suffix, keep, add in (
        ("zioni", 5, "tion"),
        ("zione", 5, "tion"),
        ("ciones", 6, "tion"),
        ("cion", 4, "tion"),
        ("enza", 4, "enc"),
        ("anza", 4, "anc"),
        ("ibile", 5, "ibil"),
        ("ible", 4, "ibil"),
        ("abile", 5, "abil"),
        ("able", 4, "abil"),
    ):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[:-keep] + add
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "y"
    elif word.endswith("sses"):
        word = word[:-2]
    elif word.endswith("ing") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3:
        word = word[:-1]
    if len(word) > 3 and word[-1] in "aeiouy":
        word = word[:-1]
        if word.endswith(("ch", "gh")):
            word = word[:-1]
    return word


# ---------------------------------------------------------------- concepts (synonym map)


@dataclass(frozen=True)
class _Phrase:
    concept: str
    words: tuple[str, ...]  # folded; a word ending in "*" is a prefix
    script: str  # non-empty for Arabic/Chinese/Cyrillic/Bengali phrases (see _script_spans)
    query_only: bool


# Chinese and Japanese are written without spaces: their phrases match as substrings.
_CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]")
_LETTER = re.compile(r"[^\W\d_]|[\u0900-\u0dff]")
_ARABIC = re.compile(r"[\u0600-\u06ff]")
SHORT_SCRIPT_PHRASE = 4  # letters: a phrase this short must be the whole word (almost)
SHORT_SCRIPT_ENDING = 3  # letters of Cyrillic or Bengali ending a short stem may take


def _fold_pattern(pattern: str) -> str:
    """A regular expression folded like the text it runs on, its escapes kept (\\W, \\D, \\S
    and \\B would turn into \\w, \\d, \\s and \\b under casefold)."""

    def fold(m: re.Match[str]) -> str:
        return m.group(0) if m.group(0).startswith("\\") else _fold(m.group(0))

    return re.sub(r"\\.|[^\\]+", fold, pattern)


def _letters(text: str) -> int:
    return len(_LETTER.findall(text))


def _token_bounds(folded: str, start: int, end: int) -> tuple[int, int]:
    """The word (run of letters) around folded[start:end]."""
    a = start
    while a > 0 and _LETTER.match(folded[a - 1]):
        a -= 1
    b = end
    while b < len(folded) and _LETTER.match(folded[b]):
        b += 1
    return a, b


class _Concepts:
    """The synonym map, compiled for matching word sequences and substrings."""

    def __init__(self, raw: dict) -> None:
        self.by_first: dict[str, list[_Phrase]] = {}
        self.prefix_first: list[_Phrase] = []
        self.script: list[_Phrase] = []
        self._first_cache: dict[str, tuple[_Phrase, ...]] = {}
        self.query_patterns: list[tuple[str, re.Pattern[str]]] = []
        # 'not' phrases: inside one, the concept's words mean something else ("ho subito").
        self.exclusions: dict[str, list[_Phrase]] = {}
        for concept, spec in sorted((raw.get("concepts") or {}).items()):
            for pattern in spec.get("query_regex") or []:
                try:
                    self.query_patterns.append((concept, re.compile(_fold_pattern(pattern))))
                except re.error:
                    continue
            for text in spec.get("not") or []:
                phrase = self._compile(concept, text, False)
                if phrase is not None:
                    self.exclusions.setdefault(concept, []).append(phrase)
            for query_only, key in ((False, "phrases"), (True, "query_only")):
                for text in spec.get(key) or []:
                    phrase = self._compile(concept, text, query_only)
                    if phrase is None:
                        continue
                    if phrase.script:
                        self.script.append(phrase)
                    elif phrase.words[0].endswith("*"):
                        self.prefix_first.append(phrase)
                    else:
                        self.by_first.setdefault(phrase.words[0], []).append(phrase)
        self.names = sorted((raw.get("concepts") or {}).keys())
        # How Arabic, Chinese, Cyrillic and Bengali words are read ("scripts" in the map).
        scripts = raw.get("scripts") or {}
        self.arabic_prefixes = frozenset(_fold(w) for w in scripts.get("arabic_prefixes") or [])
        self.arabic_suffixes = frozenset(_fold(w) for w in scripts.get("arabic_suffixes") or [])
        self.function_words = frozenset(_fold(w) for w in scripts.get("function_words") or [])
        self.function_chars = frozenset(_fold("".join(scripts.get("function_chars") or [])))
        self.ignored_starts = tuple(_fold(w) for w in scripts.get("ignored_word_starts") or [])
        # Chat shorthand ("nn" for "non", "u" for "you"), read as the word in queries only.
        self.abbreviations = {
            _fold(short): _fold(word)
            for short, word in (raw.get("abbreviations") or {}).items()
            if not short.startswith("_") and isinstance(word, str)
        }
        self.distinct = frozenset(
            "§" + name for name, spec in (raw.get("concepts") or {}).items() if spec.get("distinct")
        )
        # A question word, not a topic ("how many", "what is"): it weighs less, a heading
        # that has it is not about something else, and coordination doesn't count it.
        self.weights = {
            "§" + name: float(spec["weight"])
            for name, spec in (raw.get("concepts") or {}).items()
            if isinstance(spec.get("weight"), (int, float))
        }
        self.other_documents = frozenset(
            "§" + name
            for name, spec in (raw.get("concepts") or {}).items()
            if spec.get("other_document")
        )
        # Concepts that headings name together ("Furto e smarrimento"): asking about one, a
        # heading that also names the other is not about something else.
        self.related: dict[str, frozenset[str]] = {
            "§" + name: frozenset("§" + r for r in spec.get("related") or [])
            for name, spec in (raw.get("concepts") or {}).items()
        }

    @staticmethod
    def _compile(concept: str, text: str, query_only: bool) -> _Phrase | None:
        folded = _fold(text).strip()
        if not folded:
            return None
        if _NON_LATIN.search(folded):
            return _Phrase(concept, (), folded, query_only)
        words = tuple(_WORD.findall(folded))
        if folded.endswith("*") and words:
            words = (*words[:-1], words[-1] + "*")
        if not words:
            return None
        return _Phrase(concept, words, "", query_only)

    def _starting_with(self, word: str) -> tuple[_Phrase, ...]:
        cached = self._first_cache.get(word)
        if cached is None:
            found = list(self.by_first.get(word, ()))
            found += [p for p in self.prefix_first if word.startswith(p.words[0][:-1])]
            cached = self._first_cache[word] = tuple(found)
        return cached

    @staticmethod
    def _word_matches(pattern: str, word: str) -> bool:
        return word.startswith(pattern[:-1]) if pattern.endswith("*") else word == pattern

    def _covers(self, phrase: _Phrase, words: list[str], start: int, end: int) -> bool:
        """Whether a match of `phrase` covers the words start..end (a 'not' phrase)."""
        n = len(phrase.words)
        for i in range(max(0, end - n), min(start, len(words) - n) + 1):
            if all(
                self._word_matches(p, w)
                for p, w in zip(phrase.words, words[i : i + n], strict=True)
            ):
                return True
        return False

    def _script_ok(self, phrase: str, folded: str, start: int, end: int) -> bool:
        """Whether an occurrence of a non-Latin phrase is the phrase, not a piece of another
        word. Chinese: always (no spaces). Arabic, Cyrillic, Bengali: the phrase starts a word
        (after an Arabic prefix: "للأجانب"); a phrase of SHORT_SCRIPT_PHRASE letters or fewer
        must also end it, up to an Arabic pronoun ending or SHORT_SCRIPT_ENDING letters of
        Cyrillic or Bengali ending ("وجه" is not in "أتوجه", "عملي" not in "عملية", "форм" not
        in "інформація")."""
        if _CJK.search(phrase):
            return True
        word_start, word_end = _token_bounds(folded, start, end)
        prefix = folded[word_start:start]
        arabic = bool(_ARABIC.search(phrase))
        if prefix and not (arabic and prefix in self.arabic_prefixes):
            return False
        if _letters(phrase) > SHORT_SCRIPT_PHRASE:
            return True
        suffix = folded[end:word_end]
        if not suffix:
            return True
        if arabic:
            return suffix in self.arabic_suffixes
        return _letters(suffix) <= SHORT_SCRIPT_ENDING

    def _script_spans(self, phrase: _Phrase, folded: str) -> list[tuple[int, int]]:
        out = []
        start = folded.find(phrase.script)
        while start >= 0:
            end = start + len(phrase.script)
            if self._script_ok(phrase.script, folded, start, end):
                out.append((start, end))
            start = folded.find(phrase.script, start + 1)
        return out

    def ignored(self, word: str) -> bool:
        """A word of another script that says nothing about the question: a function word, or
        Milan, Italy, Italian (after an Arabic prefix too: "بميلانو", "الايطالية")."""
        if word in self.function_words:
            return True
        prefixes = sorted(self.arabic_prefixes, key=len, reverse=True)
        return any(
            word.startswith(prefix) and word[len(prefix) :].startswith(self.ignored_starts)
            for prefix in [*prefixes, ""]
        )

    def match(self, words: list[str], folded: str, query: bool) -> list[tuple[str, int, int]]:
        """Concept matches as (concept, start, end) with word positions; (concept, -1, -1) for
        Arabic/Chinese phrases and query patterns (ages). A match inside a longer match is
        dropped ("residence permit" is a permit, not also a residence), and so is a match
        inside one of its concept's 'not' phrases ("ho subito un furto" is not urgent)."""
        return [
            (c, a, b) if not is_script else (c, -1, -1)
            for a, b, c, is_script in self.spans(words, folded, query)
        ]

    def spans(self, words: list[str], folded: str, query: bool) -> list[tuple[int, int, str, bool]]:
        """match() with positions: (start, end, concept, is_script), word positions for
        Latin-script phrases, character positions in `folded` for the others and patterns."""
        spans: list[tuple[int, int, str, bool]] = []
        for i, word in enumerate(words):
            for phrase in self._starting_with(word):
                if phrase.query_only and not query:
                    continue
                n = len(phrase.words)
                if i + n <= len(words) and all(
                    self._word_matches(p, w)
                    for p, w in zip(phrase.words[1:], words[i + 1 : i + n], strict=True)
                ):
                    spans.append((i, i + n, phrase.concept, False))
        has_script = bool(self.script and _NON_LATIN.search(folded))
        if has_script:
            for phrase in self.script:
                if phrase.query_only and not query:
                    continue
                for a, b in self._script_spans(phrase, folded):
                    spans.append((a, b, phrase.concept, True))
        if query:
            for concept, pattern in self.query_patterns:
                for m in pattern.finditer(folded):
                    spans.append((m.start(), m.end(), concept, True))
        if self.exclusions:

            def excluded(span: tuple[int, int, str, bool]) -> bool:
                start, end, concept, script = span
                for phrase in self.exclusions.get(concept, ()):
                    if script and phrase.script:
                        found = self._script_spans(phrase, folded)
                        if any(a <= start and end <= b for a, b in found):
                            return True
                    elif not script and not phrase.script:
                        if self._covers(phrase, words, start, end):
                            return True
                return False

            spans = [s for s in spans if not excluded(s)]
        kept = []
        for s in spans:
            inside_longer = any(
                o is not s
                and o[3] == s[3]
                and o[0] <= s[0]
                and s[1] <= o[1]
                and (o[1] - o[0]) > (s[1] - s[0])
                for o in spans
            )
            if not inside_longer:
                kept.append(s)
        return kept


@functools.lru_cache(maxsize=4)
def _concepts(signature: tuple) -> _Concepts:
    try:
        raw = json.loads(SYNONYMS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    return _Concepts(raw)


def _weighted_terms(
    concepts: _Concepts, text: str, query: bool, fix: Callable[[str], str] | None = None
) -> list[tuple[str, float]]:
    """(term, weight) pairs of a text, the same way for passages and queries.

    Concepts ("§lost") weigh 1. A word that is part of a concept phrase ("lost", "ID card",
    "via Larga", the "check" of "check-in") weighs COVERED_WEIGHT: the concept carries the
    meaning in every language, the word only breaks ties, so an English word doesn't pull a
    query to the few English pages and "check the delivery" doesn't find "check-in"."""
    folded = _IDENTIFIER.sub(" ", _fold(_plain(text)))
    found = list(_WORD.finditer(folded))
    words = [m.group(0) for m in found]
    if query and concepts.abbreviations:
        words = [concepts.abbreviations.get(w, w) for w in words]
    if fix is not None:
        words = [fix(w) for w in words]
    spans = concepts.spans(words, folded, query)
    covered = {i for a, b, _, script in spans if not script for i in range(a, b)}
    # Words inside an Arabic, Chinese, Cyrillic or Bengali phrase or an age pattern: the
    # concept carries them too.
    chars = [(a, b) for a, b, _, script in spans if script]
    covered |= {
        i for i, m in enumerate(found) if any(m.start() < b and a < m.end() for a, b in chars)
    }
    out: list[tuple[str, float]] = []
    for i, word in enumerate(words):
        if word in _STOPWORDS or (len(word) < 2 and not word.isdigit()):
            continue
        weight = COVERED_WEIGHT if i in covered else 1.0
        out.append((_stem(word), weight * NUMBER_WEIGHT if word.isdigit() else weight))
    out.extend(("§" + c, concepts.weights.get("§" + c, 1.0)) for _, _, c, _ in spans)
    return out


def _script_gaps(concepts: _Concepts, query: str) -> float:
    """How many words of a query's Arabic, Chinese, Cyrillic or Bengali text no concept reads
    (function words apart; Chinese counted as one word per two characters). The pages are in
    Italian and English: those words can only be read through the concept map, and when the
    map misses them the passages hold less of the question than the concepts suggest."""
    folded = _fold(_plain(query))
    if not _NON_LATIN.search(folded):
        return 0.0
    found = list(_WORD.finditer(folded))
    words = [m.group(0) for m in found]
    chars = [(a, b) for a, b, _, script in concepts.spans(words, folded, True) if script]
    gaps = 0.0
    for m in found:
        word = m.group(0)
        if not _NON_LATIN.search(word) or concepts.ignored(word):
            continue
        if _CJK.search(word):
            loose = sum(
                1
                for i in range(m.start(), m.end())
                if folded[i] not in concepts.function_chars
                and not any(a <= i < b for a, b in chars)
            )
            gaps += loose / 2
        elif not any(m.start() < b and a < m.end() for a, b in chars):
            gaps += 1
    return gaps


# ---------------------------------------------------------------- pages and passages


@dataclass
class _Page:
    source_id: str
    title: str
    publisher: str
    url: str
    saved_at: str
    kind: str
    lang: str
    services: tuple[str, ...]
    updated_at: str  # the page's own date ("Ultimo aggiornamento: 02/10/2026"), ISO, or ""
    content_hash: str
    hash_ok: bool
    body: str


@dataclass
class _Passage:
    passage_id: str
    source_id: str
    heading: str
    path: tuple[str, ...]
    text: str
    start: int
    end: int
    words: int
    question: bool
    label: bool = False  # its own heading labels the section above it (see _heading_levels)


def _front_matter(text: str) -> tuple[dict, str]:
    """Split the YAML front matter written by `onevisit ingest` (flat keys, simple lists).

    The body is what follows the closing '---' without leading blank lines, as in
    onevisit_knowledge.split_front_matter, so content_hash is computed on the same text."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            meta: dict = {}
            key = None
            for line in lines[1:index]:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("- ") and key:
                    if not isinstance(meta.get(key), list):
                        meta[key] = []
                    meta[key].append(_scalar(stripped[2:]))
                    continue
                if ":" in line and not line[:1].isspace():
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()
                    meta[key] = [] if value == "[]" else (_scalar(value) if value else None)
            return meta, "".join(lines[index + 1 :]).lstrip("\n")
    return {}, text


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        inner = value[1:-1]
        return inner.replace("''", "'") if value[0] == "'" else inner.replace('\\"', '"')
    return value


def _language(body: str) -> str:
    words = _WORD.findall(body.lower()[:20000])
    italian = sum(w in _IT_MARKERS for w in words)
    english = sum(w in _EN_MARKERS for w in words)
    return "en" if english > italian else "it"


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("gennaio", "january", "enero", "janvier"),
            ("febbraio", "february", "febrero", "fevrier"),
            ("marzo", "march", "marzo", "mars"),
            ("aprile", "april", "abril", "avril"),
            ("maggio", "may", "mayo", "mai"),
            ("giugno", "june", "junio", "juin"),
            ("luglio", "july", "julio", "juillet"),
            ("agosto", "august", "agosto", "aout"),
            ("settembre", "september", "septiembre", "septembre"),
            ("ottobre", "october", "octubre", "octobre"),
            ("novembre", "november", "noviembre", "novembre"),
            ("dicembre", "december", "diciembre", "decembre"),
        ]
    )
    for m in names
}
_DATE = r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})|(\d{1,2})\s+([a-z]+)\s+(\d{4})"
# "Ultimo aggiornamento: 02/10/2026", "Data:\n19 gennaio 2026", "(modificato il 18/02/2026)"
_DATE_LABEL = re.compile(
    r"(?:ultimo aggiornamento|ultima modifica|aggiornato (?:al|il)|modificato il|last updated|"
    r"updated|data\s*:)"
    r"[\s:>*_]*(?:" + _DATE + ")"
)
_URL_DATE = re.compile(r"(?<!\d)(\d{2})-(\d{2})-(\d{4})(?!\d)")
_LINE_DATE = re.compile(r"^\s*(\d{2})/(\d{2})/(\d{4})\s*$", re.MULTILINE)


def _iso(day: str, month: str, year: str) -> str:
    try:
        number = int(month) if month.isdigit() else _MONTHS.get(month, 0)
        return datetime.date(int(year), number, int(day)).isoformat()
    except ValueError:
        return ""


def _page_date(body: str, url: str = "") -> str:
    """The page's own date, ISO, or "": the latest "Ultimo aggiornamento" / "Data:" /
    "last updated" date in it; else a date in its address (circ-004-servdemo-03-04-2017.pdf);
    else a date alone on a line near the top (a circular's protocol date)."""
    folded = _fold(body)
    found = []
    for m in _DATE_LABEL.finditer(folded):
        parts = m.groups()
        found.append(_iso(*parts[:3]) if parts[0] else _iso(*parts[3:]))
    found = [d for d in found if d]
    if found:
        return max(found)
    m = _URL_DATE.search(url)
    if m and _iso(*m.groups()):
        return _iso(*m.groups())
    head = "\n".join(body.splitlines()[:150])
    m = _LINE_DATE.search(head)
    return _iso(*m.groups()) if m else ""


def _staleness(page: _Page, as_of: str) -> float:
    """The STALE factor of an old news item or circular, else 1."""
    days, factor = STALE.get(page.kind, (0, 1.0))
    if not days or not page.updated_at or not as_of:
        return 1.0
    age = datetime.date.fromisoformat(as_of) - datetime.date.fromisoformat(page.updated_at)
    return factor if age.days > days else 1.0


def _clean_heading(text: str) -> str:
    text = _plain(text).replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", text).strip(" #")


def _block_kind(lines: list[str]) -> str:
    """'noise' (menus, breadcrumbs, share buttons, images), 'links' (only links) or 'text'."""
    stripped = [ln.strip() for ln in lines if ln.strip()]
    if all(
        _IMAGE_ONLY.match(ln) or _LIST_PREFIX.sub("", ln).lower() in _BOILERPLATE for ln in stripped
    ):
        return "noise"
    link_only = [bool(_LINK_ONLY.match(ln)) for ln in stripped]
    # A breadcrumb: a list that starts with a link to the home page.
    first = _MD_LINK.match(_LIST_PREFIX.sub("", stripped[0]))
    if (
        link_only[0]
        and first
        and first.group(1).strip().lower() in ("home", "homepage", "home page")
        and all(_LIST_PREFIX.match(ln) for ln in stripped)
    ):
        return "noise"
    # In-page menus, share buttons: mostly links, the rest a few words, no sentence.
    if (
        len(stripped) >= 2
        and sum(link_only) * 2 >= len(stripped)
        and all(
            lo or (len(_words(ln)) <= 8 and not re.search(r"[.:;?!]\s*$", ln))
            for lo, ln in zip(link_only, stripped, strict=True)
        )
    ):
        return "noise"
    if all(lo or _IMAGE_ONLY.match(ln) for lo, ln in zip(link_only, stripped, strict=True)):
        return "links"
    return "text"


@dataclass
class _Unit:
    start: int
    end: int
    words: int
    kind: str  # text, links, noise, question


def _units(body: str, start: int, end: int) -> list[_Unit]:
    """Blocks separated by blank lines between `start` and `end`, as character spans."""
    units: list[_Unit] = []
    block: list[tuple[int, str]] = []

    def close() -> None:
        if not block:
            return
        first_pos, first = block[0]
        last_pos, last = block[-1]
        a = first_pos + (len(first) - len(first.lstrip()))
        b = last_pos + len(last.rstrip())
        if b > a:
            text = body[a:b]
            units.append(_Unit(a, b, len(_words(text)), _block_kind([ln for _, ln in block])))
        block.clear()

    pos = start
    for line in body[start:end].splitlines(keepends=True):
        if line.strip():
            block.append((pos, line))
        else:
            close()
        pos += len(line)
    close()
    return units


def _split_unit(body: str, unit: _Unit, max_words: int) -> list[_Unit]:
    """A block longer than max_words, split at line ends, then sentence ends, then words."""
    if unit.words <= max_words:
        return [unit]
    for pattern in (re.compile(r"\n"), _SENTENCE_END, re.compile(r"\s+")):
        pieces: list[_Unit] = []
        cursor = unit.start
        text = body[unit.start : unit.end]
        for m in pattern.finditer(text):
            cut = unit.start + m.start()
            if cut > cursor:
                piece = body[cursor:cut]
                pieces.append(_Unit(cursor, cut, len(_words(piece)), unit.kind))
            cursor = unit.start + m.end()
        if cursor < unit.end:
            pieces.append(_Unit(cursor, unit.end, len(_words(body[cursor : unit.end])), unit.kind))
        if len(pieces) > 1:
            out: list[_Unit] = []
            for piece in pieces:
                out.extend(_split_unit(body, piece, max_words))
            return _regroup(out, max_words)
    return [unit]


def _regroup(units: list[_Unit], max_words: int) -> list[_Unit]:
    """Pieces of one block packed back into spans of at most max_words."""
    out: list[_Unit] = []
    for u in units:
        if out and out[-1].words + u.words <= max_words:
            last = out[-1]
            out[-1] = _Unit(last.start, u.end, last.words + u.words, last.kind)
        else:
            out.append(u)
    return out


def _pack(units: list[_Unit], max_words: int) -> list[list[_Unit]]:
    """Consecutive units grouped into passages of MIN_WORDS..max_words when possible."""
    groups: list[list[_Unit]] = []
    current: list[_Unit] = []
    count = 0
    hard_max = max(HARD_MAX_WORDS, max_words)
    for unit in units:
        too_long = current and count + unit.words > max_words
        if too_long and (count >= MIN_WORDS or count + unit.words > hard_max):
            groups.append(current)
            current, count = [], 0
        current.append(unit)
        count += unit.words
    if current:
        if groups and count < MIN_WORDS and sum(u.words for u in groups[-1]) + count <= hard_max:
            groups[-1].extend(current)
        else:
            groups.append(current)
    return groups


_LABEL_LEVEL = 7  # deeper than any Markdown heading: a label is popped by the next heading


def _heading_levels(body: str) -> list[int]:
    """The level each heading of a page has in its outline, in page order.

    Mostly the number of '#'s. Some pages put a tab's label one level ABOVE the section that
    holds it (the City's service pages: "### Carta d'identità provvisoria", its text, then
    "## Documenti da presentare" for the provisional card's own list). Read literally, the
    label would end that section and own every section after it. A heading is read as a
    label of the section before it (a leaf, closed by the next heading) when it comes right
    after a heading one level deeper and either (a) that heading has no text of its own (an
    empty "### Altra documentazione" followed by "## Documenti aggiuntivi ..." is a container,
    not an empty section) or (b) the same title appears more than once at its level in the
    page (tab labels repeat, section titles don't). A heading of the same level right after
    a label, with no other heading between, is the next tab: a label too. A repeated title
    is a label wherever it appears, the first time included ("## Documenti da presentare"
    under the H1, before the page's ### sections)."""
    found: list[tuple[int, str, bool]] = []  # level, folded title, has text before next heading
    for line in body.splitlines():
        m = _HEADING.match(line)
        if m:
            found.append((len(m.group(1)), _fold(_clean_heading(m.group(2))), False))
        elif found and line.strip() and not found[-1][2]:
            found[-1] = (found[-1][0], found[-1][1], True)
    counts: dict[tuple[int, str], int] = {}
    for level, title, _ in found:
        counts[(level, title)] = counts.get((level, title), 0) + 1
    repeated_inverted = {
        (level, title)
        for i, (level, title, _) in enumerate(found)
        if i and counts[(level, title)] > 1 and found[i - 1][0] == level + 1
    }
    levels: list[int] = []
    for i, (level, title, _) in enumerate(found):
        previous = found[i - 1] if i else None
        label = (level, title) in repeated_inverted
        if previous and not label:
            after_empty = previous[0] == level + 1 and not previous[2]
            next_tab = levels[-1] == _LABEL_LEVEL and previous[0] == level
            label = after_empty or next_tab
        levels.append(_LABEL_LEVEL if label and level > 1 else level)
    return levels


def _passages(page: _Page, faq_page: bool) -> list[_Passage]:
    """Cut a page body into passages: sections by heading, then blocks packed to size.

    Every passage is body[start:end] of the page; a question passage starts at the
    question's text (after the '#'s) and runs through its answer."""
    body = page.body
    lines = body.splitlines(keepends=True)
    sections: list[tuple[tuple[str, ...], bool, int, int, int, bool]] = []
    stack: list[tuple[int, str]] = []
    path: tuple[str, ...] = ()
    question = label = False
    content_start = 0
    question_start = -1
    pos = 0
    levels = iter(_heading_levels(body))
    for line in lines:
        m = _HEADING.match(line.rstrip("\n"))
        if m:
            sections.append((path, question, content_start, pos, question_start, label))
            level = next(levels, len(m.group(1)))
            while stack and stack[-1][0] >= level:
                stack.pop()
            heading = _clean_heading(m.group(2))
            if heading:
                stack.append((level, heading))
            path = tuple(h for _, h in stack)
            label = bool(heading) and level == _LABEL_LEVEL
            question = bool(heading) and (faq_page or heading.endswith("?"))
            question_start = pos + m.start(2) if question else -1
            content_start = pos + len(line)
        pos += len(line)
    sections.append((path, question, content_start, len(body), question_start, label))

    out: list[_Passage] = []
    for path, is_question, start, end, q_start, is_label in sections:
        units = _units(body, start, end)
        if not any(u.kind == "text" for u in units):
            continue
        max_words = FAQ_MAX_WORDS if is_question else MAX_WORDS
        segments: list[list[_Unit]] = [[]]
        if is_question:
            q_end = q_start + len(body[q_start:start].rstrip())
            q_text = body[q_start:q_end]
            segments[0].append(_Unit(q_start, q_end, len(_words(q_text)), "question"))
        for unit in units:
            if unit.kind == "noise":
                segments.append([])
                continue
            segments[-1].extend(_split_unit(body, unit, MAX_WORDS))
        for segment in segments:
            for group in _pack(segment, max_words):
                if not any(u.kind == "text" for u in group):
                    continue
                a, b = group[0].start, group[-1].end
                text = body[a:b]
                words = len(_words(text))
                if group[0].kind != "question" and (
                    words < 3 or (path and _words(text) == _words(path[-1]))
                ):
                    continue  # a caption or a repeated title, nothing to quote
                out.append(
                    _Passage(
                        passage_id=f"{page.source_id}#{len(out) + 1}",
                        source_id=page.source_id,
                        heading=" > ".join(path),
                        path=path,
                        text=text,
                        start=a,
                        end=b,
                        words=words,
                        question=is_question,
                        label=is_label,
                    )
                )
    return out


# ---------------------------------------------------------------- index


@dataclass
class _Index:
    pages: dict[str, _Page]
    passages: list[_Passage]
    postings: dict[str, list[tuple[int, float]]]
    norms: list[float]
    idf: dict[str, float]
    priors: list[float]
    topics: list[frozenset[str]]  # concepts of a passage's own heading (its question)
    minority: frozenset[str]  # words found only in pages of a minority language (English)
    vocabulary: dict[str, int]  # folded words of the pages and the concept map, with counts
    deletions: dict[str, tuple[str, ...]]  # a word minus one letter -> vocabulary words
    page_counts: dict[str, int]  # folded words of the pages only, with counts
    concept_words: frozenset[str]  # words of the concept map's Latin-script phrases
    common: frozenset[str]  # concepts in more than half of the passages ("carta d'identità")
    as_of: str  # the latest date a page was saved: "now" for the index (stale news)
    build_ms: float
    signature: tuple


def _sources_rows() -> dict[str, dict]:
    path = DATA / "sources.csv"
    try:
        with path.open(encoding="utf-8", newline="") as f:
            return {row["id"]: row for row in csv.DictReader(f) if row.get("id")}
    except OSError:
        return {}


def _stat(path: pathlib.Path) -> tuple:
    try:
        st = path.stat()
    except OSError:
        return (path.name, 0, 0)
    return (path.name, st.st_mtime_ns, st.st_size)


def _signature() -> tuple:
    """What the index depends on: the page files, sources.csv and the synonym map."""
    pages = sorted((DATA / "pages").glob("*.md"))
    return (
        str(DATA),
        tuple(_stat(p) for p in pages),
        _stat(DATA / "sources.csv"),
        _stat(SYNONYMS_FILE),
    )


def _index() -> _Index:
    return _build(_signature())


@functools.lru_cache(maxsize=2)
def _build(signature: tuple) -> _Index:
    started = time.perf_counter()
    concepts = _concepts(signature[3])
    rows = _sources_rows()
    pages: dict[str, _Page] = {}
    passages: list[_Passage] = []
    for path in sorted((DATA / "pages").glob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        meta, body = _front_matter(raw)
        source_id = str(meta.get("source_id") or path.stem)
        row = rows.get(source_id, {})
        if row.get("status") and row["status"] != "ok":
            continue
        kind = row.get("kind") or ("faq" if source_id.startswith("cie-faq-") else "page")
        kind = next(
            (k for pattern, k in KIND_BY_ID if fnmatch.fnmatchcase(source_id, pattern)), kind
        )
        h1 = next((m.group(2) for m in map(_HEADING.match, body.splitlines()) if m), "")
        declared = str(meta.get("content_hash") or "")
        actual = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
        services = meta.get("servizio") or []
        page = _Page(
            source_id=source_id,
            title=row.get("title") or _clean_heading(h1) or source_id,
            publisher=row.get("publisher") or str(meta.get("ente") or ""),
            url=str(meta.get("url") or row.get("url") or ""),
            saved_at=str(meta.get("verified_at") or row.get("retrieved_at") or ""),
            kind=kind,
            lang=_language(body),
            services=tuple(services) if isinstance(services, list) else (str(services),),
            updated_at=_page_date(body, str(meta.get("url") or row.get("url") or "")),
            content_hash=declared,
            hash_ok=(not declared) or declared == actual,
            body=body,
        )
        pages[source_id] = page
        passages.extend(_passages(page, faq_page=kind == "faq"))

    doc_terms: list[dict[str, float]] = []
    lengths: list[float] = []
    topics: list[frozenset[str]] = []
    for passage in passages:
        page = pages[passage.source_id]
        tf: dict[str, float] = {}

        def add(text: str, weight: float, tf: dict[str, float] = tf) -> int:
            terms = _weighted_terms(concepts, text, query=False)
            for term, w in terms:
                tf[term] = tf.get(term, 0.0) + weight * w
            return len(terms)

        length = add(passage.text, 1.0)
        topic: frozenset[str] = frozenset()
        if passage.path:
            own = QUESTION_WEIGHT if passage.question else HEADING_WEIGHT
            # A tab label's section is the passage's own section too: the provisional card's
            # "Documenti da presentare" is about the provisional card.
            mine = passage.path[-2:] if passage.label else passage.path[-1:]
            for heading_text in mine:
                length += add(heading_text, own)
                heading = _weighted_terms(concepts, heading_text, query=False)
                topic |= frozenset(
                    t for t, _ in heading if t.startswith("§") and t not in concepts.weights
                )
            for parent in passage.path[: -len(mine)]:
                add(parent, PARENT_HEADING_WEIGHT)
        # The page title, unless the headings already say it (or it is the FAQ's question).
        if page.kind != "faq" and not set(_words(page.title)) <= {
            w for h in passage.path for w in _words(h)
        }:
            add(page.title, TITLE_WEIGHT)
        doc_terms.append(tf)
        lengths.append(max(float(length), LENGTH_FLOOR))
        topics.append(topic)

    n = len(passages)
    average = (sum(lengths) / n) if n else 1.0
    postings: dict[str, list[tuple[int, float]]] = {}
    for i, tf in enumerate(doc_terms):
        for term, value in tf.items():
            postings.setdefault(term, []).append((i, value))
    # IDF among the passages of the term's language: "card" is rare in a mostly Italian
    # corpus but common in the English pages, and must not pull English queries to them.
    langs = [pages[p.source_id].lang for p in passages]
    per_lang: dict[str, int] = {}
    for lang in langs:
        per_lang[lang] = per_lang.get(lang, 0) + 1
    idf: dict[str, float] = {}
    minority: set[str] = set()
    for term, plist in postings.items():
        counts: dict[str, int] = {}
        for i, _ in plist:
            counts[langs[i]] = counts.get(langs[i], 0) + 1
        lang, top = max(counts.items(), key=lambda item: (item[1], item[0]))
        # A concept is the same term in every language: its IDF is over all passages.
        one_language = top >= ONE_LANGUAGE_SHARE * len(plist) and not term.startswith("§")
        total = per_lang[lang] if one_language else n
        if one_language and per_lang[lang] < MINORITY_SHARE * n:
            minority.add(term)
        df = len(plist)
        idf[term] = math.log(1 + (total - df + 0.5) / (df + 0.5))
    # Concepts in most passages ("carta d'identità") say nothing about a question's topic.
    common = {t for t, plist in postings.items() if t.startswith("§") and len(plist) > n / 5}
    topics = [t - common for t in topics]
    norms = [K1 * (1 - B + B * length / average) for length in lengths]
    as_of = max((p.saved_at for p in pages.values() if _ISO_DATE.fullmatch(p.saved_at)), default="")
    priors = [
        KIND_PRIOR.get(pages[p.source_id].kind, 1.0)
        * PUBLISHER_PRIOR.get(pages[p.source_id].publisher, 1.0)
        * _staleness(pages[p.source_id], as_of)
        for p in passages
    ]
    vocabulary, deletions, page_counts, concept_words = _spelling(passages, pages, concepts)
    build_ms = (time.perf_counter() - started) * 1000
    return _Index(
        pages,
        passages,
        postings,
        norms,
        idf,
        priors,
        topics,
        frozenset(minority),
        vocabulary,
        deletions,
        page_counts,
        concept_words,
        frozenset(t for t, plist in postings.items() if t.startswith("§") and len(plist) > n / 2),
        as_of,
        build_ms,
        signature,
    )


# ---------------------------------------------------------------- spelling


def _spelling(
    passages: list[_Passage], pages: dict[str, _Page], concepts: _Concepts
) -> tuple[dict[str, int], dict[str, tuple[str, ...]], dict[str, int], frozenset[str]]:
    """The words a query may be corrected to (pages, headings, titles, the concept map's
    Latin-script words) and, for each, every form with one letter removed (symmetric delete:
    two words one edit apart share a form, a swap of two letters included), plus the counts
    in the pages alone and the words of the concept map."""
    vocabulary: dict[str, int] = {}

    def count(text: str) -> None:
        for word in _WORD.findall(_fold(_plain(text))):
            if len(word) >= SPELL_MIN_WORD - 1 and word.isascii() and word.isalpha():
                vocabulary[word] = vocabulary.get(word, 0) + 1

    for passage in passages:
        count(passage.text)
        count(" ".join(passage.path))
    for page in pages.values():
        count(page.title)
    page_counts = dict(vocabulary)
    concept_words: set[str] = set()
    for phrases in concepts.by_first.values():
        for phrase in phrases:
            for word in phrase.words:
                count(word.rstrip("*"))
                concept_words.add(word.rstrip("*"))
    # Page words a prefix phrase reads ("smarrita" for "smarri*") are concept words too.
    starts = tuple(p.words[0][:-1] for p in concepts.prefix_first)
    concept_words |= {w for w in vocabulary if starts and w.startswith(starts)}
    deletions: dict[str, list[str]] = {}
    for word in vocabulary:
        for i in range(len(word)):
            deletions.setdefault(word[:i] + word[i + 1 :], []).append(word)
    return (
        vocabulary,
        {key: tuple(words) for key, words in deletions.items()},
        page_counts,
        frozenset(concept_words) - frozenset(_STOPWORDS),
    )


def _edit(a: str, b: str) -> str:
    """How b differs from a by one typing error: "substitution", "transposition",
    "insertion" (b has a letter more), "deletion"; "" when it is not one error away."""
    if a == b or abs(len(a) - len(b)) > 1:
        return ""
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return "substitution"
        swapped = (
            len(diff) == 2
            and diff[1] == diff[0] + 1
            and a[diff[0]] == b[diff[1]]
            and a[diff[1]] == b[diff[0]]
        )
        return "transposition" if swapped else ""
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    if any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_))):
        return "insertion" if len(b) > len(a) else "deletion"
    return ""


def _one_edit(a: str, b: str) -> bool:
    """True when b is a with one letter changed, added, removed, or two neighbours swapped."""
    return bool(_edit(a, b))


def _correct(index: _Index, word: str) -> str:
    """A query word that no page and no concept knows, read as the known word one typing
    error away ("expierd" -> "expired", "documneti" -> "documenti"); else the word itself.

    Same first letter, at least SPELL_MIN_WORD letters, the most frequent candidate. A real
    word the pages don't have must not become another real word: a verb or participle form
    ("votare", "avuto", "lending") is never read with one letter changed ("volare", "aiuto",
    "landing"); a correction that turns the word into a concept ("smarita" -> "smarrita")
    needs a letter added, dropped or swapped and SPELL_CONCEPT_MIN_WORD letters; any other
    correction needs a word found SPELL_MIN_COUNT times in the pages ("treno" is not
    "trento", which one page names once)."""
    if (
        len(word) < SPELL_MIN_WORD
        or not word.isascii()
        or not word.isalpha()
        or word in index.vocabulary
        or word in _STOPWORDS
        or _stem(word) in index.postings
    ):
        return word
    keys = {word} | {word[:i] + word[i + 1 :] for i in range(len(word))}
    candidates = set()
    for key in keys:
        candidates.update(index.deletions.get(key, ()))
        if key in index.vocabulary:
            candidates.add(key)
    inflected = word.endswith(_INFLECTIONS)
    best = []
    for c in candidates:
        kind = _edit(word, c) if c[0] == word[0] else ""
        if not kind or (kind == "substitution" and inflected):
            continue
        if c in index.concept_words:
            if kind == "substitution" or len(word) < SPELL_CONCEPT_MIN_WORD:
                continue
        elif index.page_counts.get(c, 0) < SPELL_MIN_COUNT:
            continue
        best.append((-index.vocabulary[c], c))
    return min(best)[1] if best else word


# ---------------------------------------------------------------- service filter


def _service_pages(index: _Index, service_id: str) -> set[str] | None:
    """Pages of a service: those its catalog cites, those whose front matter names it, and
    the ids in SERVICE_PAGES. None for a service nobody knows."""
    known = False
    allowed: set[str] = set()
    path = DATA / "services" / f"{service_id}.json"
    if path.exists():
        known = True
        with contextlib.suppress(OSError, json.JSONDecodeError):  # being rewritten: skip it
            allowed |= _cited_sources(json.loads(path.read_text(encoding="utf-8")))
    patterns = SERVICE_PAGES.get(service_id, ())
    if patterns:
        known = True
    for sid, page in index.pages.items():
        if service_id in page.services or any(fnmatch.fnmatchcase(sid, p) for p in patterns):
            allowed.add(sid)
            known = True
    return allowed if known else None


def _cited_sources(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("source_id", "quote_source_id") and isinstance(value, str):
                found.add(value)
            elif key == "source_ids" and isinstance(value, list):
                found.update(v for v in value if isinstance(v, str))
            else:
                found |= _cited_sources(value)
    elif isinstance(node, list):
        for item in node:
            found |= _cited_sources(item)
    return found


# ---------------------------------------------------------------- public API


def _result(index: _Index, i: int, score: float | None) -> dict:
    passage = index.passages[i]
    page = index.pages[passage.source_id]
    out = {
        "source_id": passage.source_id,
        "passage_id": passage.passage_id,
        "title": page.title,
        "publisher": page.publisher,
        "url": page.url,
        "saved_at": page.saved_at,
        "updated_at": page.updated_at,
        "kind": page.kind,
        "lang": page.lang,
        "heading": passage.heading,
        "text": passage.text,
    }
    if score is not None:
        out["score"] = round(score, 3)
    return out


def query_terms(query: str) -> dict[str, float]:
    """The weighted terms a query searches for: its stemmed words and its concepts ("§lost")."""
    terms: dict[str, float] = {}
    index = _index()
    concepts = _concepts(_stat(SYNONYMS_FILE))
    fix = functools.partial(_correct, index)
    for term, weight in _weighted_terms(concepts, query, query=True, fix=fix):
        terms[term] = max(terms.get(term, 0.0), weight)
    return terms


def _rank(
    query: str, service_id: str | None, lang: str | None
) -> tuple[_Index, list[tuple[float, str, int]], dict[str, float], dict[int, float]] | None:
    """Every matching passage as (-score, source_id, index), best first, plus the query's
    terms; None when the query or the service gives nothing to search."""
    if not isinstance(query, str) or not query.strip():
        return None
    index = _index()
    allowed = None
    if service_id:
        allowed = _service_pages(index, service_id)
        if not allowed:
            return None
    concepts = _concepts(_stat(SYNONYMS_FILE))
    terms = query_terms(query)
    asked = {t for t in terms if t.startswith("§") and t not in concepts.weights}
    near = asked.union(*(concepts.related.get(t, frozenset()) for t in asked))
    local = bool(asked & LOCAL_CONCEPTS)
    scores: dict[int, float] = {}
    held: dict[int, float] = {}  # the IDF of the query terms the passage holds, once each
    found: dict[int, int] = {}  # concepts asked that the passage has
    for term, weight in terms.items():
        plist = index.postings.get(term)
        if not plist:
            continue
        if term in index.minority:
            weight *= MINORITY_LANGUAGE_WEIGHT
        idf = index.idf[term] * weight
        concept = term in asked
        for i, tf in plist:
            scores[i] = scores.get(i, 0.0) + idf * tf * (K1 + 1) / (tf + index.norms[i])
            held[i] = held.get(i, 0.0) + idf
            if concept:
                found[i] = found.get(i, 0) + 1
    ranked = []
    lang = (lang or "").lower()[:2]
    for i, score in scores.items():
        passage = index.passages[i]
        if allowed is not None and passage.source_id not in allowed:
            continue
        score *= index.priors[i]
        if lang and index.pages[passage.source_id].lang == lang:
            score *= LANG_BOOST
        if local and index.pages[passage.source_id].publisher == LOCAL_PUBLISHER:
            score *= LOCAL_BOOST
        if len(asked) >= 2:
            score *= 1 - COORDINATION + COORDINATION * found.get(i, 0) / len(asked)
        extra = index.topics[i] - near  # a section about something the query didn't ask
        if extra:
            factor = 1.0
            for topic in extra:
                distinct = topic in concepts.distinct
                factor *= DISTINCT_TOPIC_PENALTY if distinct else EXTRA_TOPIC_PENALTY
            score *= max(EXTRA_TOPIC_FLOOR, factor)
        ranked.append((-score, passage.source_id, i))
    ranked.sort()
    return index, ranked, terms, held


def _attainable(index: _Index, terms: dict[str, float], gaps: float = 0.0) -> float:
    """What a passage of average length holding every query term once would score. A Latin-
    script word no page has counts as the rarest word would ("weather" in "what's the weather
    tomorrow?"): the passages can't hold it, so they answer less of the question. Arabic,
    Chinese, Cyrillic and Bengali words count through their concepts, and each of their words
    no concept reads (`gaps`, from _script_gaps) as SCRIPT_GAP_WEIGHT of an unseen word: an
    Arabic question whose only concept is "ID card" is not answered by any ID card page."""
    n = len(index.passages)
    unseen = math.log(1 + (n - 1 + 0.5) / 1.5) if n else 0.0
    total = gaps * SCRIPT_GAP_WEIGHT * unseen
    for term, weight in terms.items():
        if term in index.idf:
            factor = MINORITY_LANGUAGE_WEIGHT if term in index.minority else 1.0
            total += index.idf[term] * weight * factor
        elif (
            weight >= 1.0  # a word inside a concept phrase is carried by the concept
            and not term.startswith("§")
            and not _NON_LATIN.search(term)
            and not term.isdigit()
        ):
            total += unseen * weight
    return total


def _gate(index: _Index, terms: dict[str, float], service_id: str | None) -> str:
    """Why no passage can be a confident answer, whatever its score: "other_document" (the
    question is about another document and not the service's own), "unknown_words" (most of
    its words are on no saved page), "weak_match" (it asks nothing but what every page is
    about: "carta?"); "" when the query passes.

    A question that names another document only as something to bring or show ("Devo
    portare il permesso di soggiorno?", "Should I bring my passport?", "Serve la tessera
    sanitaria?") is about this service's documents: it passes."""
    concepts = _concepts(_stat(SYNONYMS_FILE))
    asked = {t for t in terms if t.startswith("§")}
    subject = SERVICE_SUBJECT.get(service_id or "")
    if (
        subject
        and "§" + subject not in asked
        and asked & concepts.other_documents
        and not asked & BRING_CONCEPTS
    ):
        return "other_document"
    informative = any(
        t in index.postings
        and (
            (t.startswith("§") and t not in index.common)
            or (not t.startswith("§") and w >= 1.0 and not t.isdigit())
        )
        for t, w in terms.items()
    )
    if not informative:
        return "weak_match"
    # Latin-script words only: Arabic, Chinese, Cyrillic and Bengali text is read through the
    # concept map, its own words are never on the (Italian and English) pages.
    words = [t for t, w in terms.items() if not t.startswith("§") and not _NON_LATIN.search(t)]
    unknown = [t for t in words if terms[t] == 1.0 and t not in index.postings and not t.isdigit()]
    if words and len(unknown) / len(words) > MAX_UNKNOWN_SHARE:
        return "unknown_words"
    return ""


def search(
    query: str,
    service_id: str | None = None,
    k: int = 5,
    lang: str | None = None,
    per_source: int = PER_SOURCE,
) -> list[dict]:
    """The k passages of the saved official pages that best answer `query`.

    Each result: source_id, passage_id, title, publisher, url, saved_at (the date the page
    was saved and checked), updated_at (the page's own date, "Ultimo aggiornamento" or the
    news item's date, ISO; "" when it has none), kind (page, faq, news, circular, pdf, form),
    lang (of the page: "it" or "en"), heading (the section path, "A > B"; for a FAQ the
    question), text (a verbatim slice of the saved page), score, confidence (the share of the
    question the passage holds, 0-1) and confident (the passage looks like an answer, not
    only like the same topic: see best_answer); "part" when the query asked two questions
    and this result answers one of them.

    `service_id` keeps only the pages of that service (an unknown service gives []).
    `lang` is the reader's language: passages in that language get a small boost; it never
    filters (the Italian pages are the authoritative ones). `per_source` caps the passages
    of one page. Empty or meaningless queries give []. Same input, same output.
    """
    return _search(query, service_id, k, lang, per_source)[0]


# A second question in the same message: after "?", or after "and" + a question word ("Qual è
# il prezzo della CIE e quali documenti devo presentare?"). Not after "and can", "and is":
# "my son is 10 and can travel?" is one question.
_QUESTION_WORDS = (
    r"quanto|quanta|quanti|quante|quale|quali|come|dove|quando|cosa|che cosa|perch[eé]|chi|"
    r"how|what|which|where|when|why|who|"
    r"cu[aá]nto|cu[aá]nta|cu[aá]ntos|cu[aá]ntas|qu[eé]|cu[aá]l|cu[aá]les|c[oó]mo|d[oó]nde|cu[aá]ndo|"
    r"combien|quel|quelle|quels|quelles|comment|o[uù]|quand|pourquoi"
)
_QUESTION_START = re.compile(r"^\W*(?:" + _QUESTION_WORDS + r")\b", re.IGNORECASE)
_SECOND_QUESTION = re.compile(
    r"\?+\s+(?=\S)|,?\s+(?:e|ed|and|y|et)\s+(?=(?:" + _QUESTION_WORDS + r")\b)", re.IGNORECASE
)


def _parts(query: str) -> list[str]:
    """The questions a message asks, when it asks more than one; else [query]. A piece that
    asks nothing of its own ("e la carta d'identità?") or is not a question ("Is it valid? I'm
    flying to Paris.") stays with the piece before it."""
    pieces = [p.strip() for p in _SECOND_QUESTION.split(query)]
    pieces = [p for p in pieces if p.strip(" ?¿,;")]
    if len(pieces) < 2:
        return [query]
    concepts = _concepts(_stat(SYNONYMS_FILE))
    index = _index()
    parts: list[str] = []
    last = len(pieces) - 1
    for i, piece in enumerate(pieces):
        # every piece but the last ended at a "?" or before "and <question word>"
        question = i < last or query.rstrip().endswith("?") or bool(_QUESTION_START.match(piece))
        terms = _weighted_terms(concepts, piece, query=True)
        own = any(
            (t.startswith("§") and t not in index.common and t not in concepts.weights)
            or (not t.startswith("§") and w >= 1.0 and not t.isdigit())
            for t, w in terms
        )
        if parts and not (own and question):
            parts[-1] = f"{parts[-1]} {piece}"
        else:
            parts.append(piece)
    parts = [p.strip(" ?¿,;") for p in parts]
    return parts if len(parts) > 1 else [query]


def _search(
    query: str,
    service_id: str | None,
    k: int,
    lang: str | None,
    per_source: int,
    split: bool = True,
) -> tuple[list[dict], str]:
    """search() plus the gate that keeps every result from being confident ("" if none).

    A message that asks two questions is searched one question at a time, and the results
    alternate (the best passage for each first): one passage that mentions both a price and
    a list of documents is rarely the answer to either. Each result then says which part
    of the message it answers ("part")."""
    if k <= 0:
        return [], ""
    parts = _parts(query) if split and isinstance(query, str) else [query]
    if len(parts) > 1:
        answers = [_search(part, service_id, k, lang, per_source, split=False) for part in parts]
        merged: list[dict] = []
        per_page: dict[str, int] = {}
        for rank in range(k):
            for part, (results, _) in zip(parts, answers, strict=True):
                if rank >= len(results) or len(merged) >= k:
                    continue
                result = results[rank]
                if any(r["passage_id"] == result["passage_id"] for r in merged):
                    continue
                if per_source and per_page.get(result["source_id"], 0) >= per_source:
                    continue
                per_page[result["source_id"]] = per_page.get(result["source_id"], 0) + 1
                merged.append(dict(result, part=part))
        gates = [gate for _, gate in answers]
        return merged, (gates[0] if all(gates) else "")
    ranked = _rank(query, service_id, lang)
    if ranked is None:
        return [], ""
    index, order, terms, held = ranked
    attainable = _attainable(index, terms, _script_gaps(_concepts(_stat(SYNONYMS_FILE)), query))
    gate = _gate(index, terms, service_id)
    top = -order[0][0] if order else 0.0
    out: list[dict] = []
    per_page: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()  # a page that repeats a section ("In evidenza"): once
    for negative, source_id, i in order:
        if per_source and per_page.get(source_id, 0) >= per_source:
            continue
        key = (source_id, " ".join(index.passages[i].text.split()))
        if key in seen:
            continue
        seen.add(key)
        per_page[source_id] = per_page.get(source_id, 0) + 1
        result = _result(index, i, -negative)
        holds = min(-negative, HELD_FACTOR * held.get(i, 0.0))
        relative = holds / attainable if attainable else 0.0
        relative = min(relative, -negative / MIN_SCORE)  # below the floor, never "all of it"
        result["confidence"] = round(min(1.0, relative), 3)
        result["confident"] = (
            not gate
            and relative >= MIN_RELATIVE
            and -negative >= max(MIN_SCORE, RELATIVE_TO_TOP * top)
        )
        out.append(result)
        if len(out) >= k:
            break
    return out, gate


def best_answer(
    query: str, service_id: str | None = None, k: int = 3, lang: str | None = None
) -> dict:
    """The passages for `query` and whether the best one looks like an answer.

    {"query", "confident": bool, "confidence": float, "reason", "passages": [...]}, where
    reason is "ok", "no_match" (nothing found), "other_document" (the question names another
    document than the service's own: a passport, a driving licence, SPID...), "unknown_words"
    (most of its words are on no saved page) or "weak_match" (the best passage holds too
    little of the question). Lexical matching cannot tell a page on the same topic from a
    page that answers: a confident result still has to be read before it is quoted."""
    passages, gate = _search(query, service_id, k, lang, PER_SOURCE)
    if not passages:
        reason = "no_match"
    elif gate:
        reason = gate
    else:
        reason = "ok" if passages[0]["confident"] else "weak_match"
    return {
        "query": query,
        "confident": reason == "ok",
        "confidence": passages[0]["confidence"] if passages else 0.0,
        "reason": reason,
        "passages": passages,
    }


def passages_for(source_id: str) -> list[dict]:
    """Every passage of one saved page, in page order (no score); [] for an unknown page."""
    index = _index()
    return [
        _result(index, i, None) for i, p in enumerate(index.passages) if p.source_id == source_id
    ]


def index_stats() -> dict:
    """Size of the index and how long it took to build, plus pages whose body no longer
    matches the content_hash written when they were ingested (edited by hand since)."""
    index = _index()
    words = [p.words for p in index.passages]
    by_lang: dict[str, int] = {}
    for page in index.pages.values():
        by_lang[page.lang] = by_lang.get(page.lang, 0) + 1
    return {
        "pages": len(index.pages),
        "passages": len(index.passages),
        "terms": len(index.postings),
        "concepts": len(_concepts(_stat(SYNONYMS_FILE)).names),
        "words_per_passage": {
            "min": min(words, default=0),
            "median": sorted(words)[len(words) // 2] if words else 0,
            "max": max(words, default=0),
        },
        "pages_by_lang": dict(sorted(by_lang.items())),
        "build_ms": round(index.build_ms, 1),
        "hash_mismatches": sorted(s for s, p in index.pages.items() if not p.hash_ok),
    }


# ---------------------------------------------------------------- Claude tool (ready to plug)

TOOL = {
    "name": "search_official_pages",
    "description": (
        "Search the official pages saved by OneVisit (Comune di Milano, its support-centre FAQ, "
        "the Ministry's CIE site, YesMilano, Polizia di Stato) for passages that answer a "
        "question. Use it for any question the checklist doesn't cover. Each result is the "
        "page's own words with source_id, url, kind (page, faq, news, circular...), the date "
        "it was saved and its own date (updated_at): answer only from these passages, cite the "
        "source_id, and if no passage answers, say you don't know and give the official page. "
        "When two passages disagree, prefer the City's current page over older news and over "
        "circulars written for registry staff, and say what the other one says. Make one "
        "search per question: if the user asks two things (the cost and the documents, a "
        "passport and the ID card), search each one separately, with its own subject in the "
        "query. Write the query in any language."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The question, in the user's words"},
            "service_id": {"type": "string", "description": "e.g. 'carta-identita' (optional)"},
            "k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    },
}


_WEAK_NOTES = {
    "other_document": "The question seems to be about another document than this service's.",
    "unknown_words": "Most of the question's words are on no saved page.",
    "weak_match": "The best passage holds little of the question.",
}


def run_tool(args: dict, lang: str | None = None) -> str:
    """JSON string for a tool_result: the passages with `confident` and `reason`, and a note
    when nothing matched or the match is weak."""
    try:
        k = max(1, min(int(args.get("k") or 5), 10))
        answer = best_answer(str(args.get("query") or ""), args.get("service_id"), k=k, lang=lang)
        results = answer["passages"]
        payload: dict = {
            "query": args.get("query"),
            "confident": answer["confident"],
            "reason": answer["reason"],
            "results": results,
        }
        if not results:
            payload["note"] = (
                "No saved official page answers this. Say you don't know and link the "
                "service's official page."
            )
        elif not answer["confident"]:
            payload["note"] = (
                _WEAK_NOTES.get(answer["reason"], "")
                + " Read the passages: if none answers the question, say you don't know and "
                "link the service's official page; never fill the gap from memory."
            ).strip()
    except Exception as e:  # report errors back to Claude instead of crashing
        payload = {"error": f"Tool error: {e}"}
    return json.dumps(payload, ensure_ascii=False)


def evaluate(path: str | pathlib.Path, k: int | None = None) -> dict:
    """Run the retrieval cases of a JSON file (data/eval/qa/search-retrieval.json): a case
    passes when one of its `expect_any` source ids is among the top k results."""
    spec = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    k = k or int(spec.get("k") or 5)
    first = hits = 0
    misses = []
    for case in spec.get("cases") or []:
        found = [
            r["source_id"]
            for r in search(case["query"], case.get("service_id"), k=k, lang=case.get("lang"))
        ]
        expected = set(case.get("expect_any") or [])
        first += bool(found) and found[0] in expected
        if expected & set(found):
            hits += 1
        else:
            misses.append({"query": case["query"], "found": found})
    total = len(spec.get("cases") or [])
    return {
        "cases": total,
        "k": k,
        "hit_at_1": round(first / total, 3) if total else 0.0,
        f"hit_at_{k}": round(hits / total, 3) if total else 0.0,
        "misses": misses,
    }


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query", nargs="?")
    parser.add_argument("--service")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--lang")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--best", action="store_true", help="say whether the match is confident")
    parser.add_argument("--eval", metavar="CASES_JSON", help="run retrieval cases, print hit rates")
    args = parser.parse_args(argv)
    if args.eval:
        print(json.dumps(evaluate(args.eval), ensure_ascii=False, indent=2))
        return
    if args.stats or not args.query:
        print(json.dumps(index_stats(), ensure_ascii=False, indent=2))
        return
    if args.best:
        answer = best_answer(args.query, args.service, args.k, args.lang)
        print(f"confident={answer['confident']} reason={answer['reason']}")
    for r in search(args.query, args.service, args.k, args.lang):
        mark = "*" if r["confident"] else " "
        print(f"{mark}[{r['source_id']}] {r['score']} ({r['confidence']})  {r['heading']}")
        print("   " + r["text"][:300].replace("\n", "\n   "))


if __name__ == "__main__":
    main()
