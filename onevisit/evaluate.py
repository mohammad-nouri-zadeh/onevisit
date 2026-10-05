"""Run the conversation scenarios in data/eval against the agent the jury sees (onevisit/agent.py).

Each scenario is one invented citizen: one or more messages and what must be true at the end
(service, the answer that defines the case, the language of the reply, requirements in the
checklist, phrases that must never appear, questions that must never be asked). Every turn
goes through `run_turn`, so the automatic check, the regeneration and the fallback are measured
too: the report counts blocked replies, regenerations, fallbacks, tool calls and latency.

    python -m onevisit.evaluate                        # needs ANTHROPIC_API_KEY; writes docs/eval-results.md
    python -m onevisit.evaluate --only cie-smarrimento-ar --transcripts docs/eval-transcripts

Real calls cost money: about 20 scenarios × 1-2 turns × a few tool steps on claude-sonnet-5-5.
The report also measures what a case costs: API requests, tokens (input, output, cache read and
write, from response.usage) and seconds per turn, and the price per scenario at the list prices
below. The tests run the same code with a fake client (tests/streamlit/test_claude_jobs.py).

    python -m onevisit.evaluate --usd-to-eur 0.92     # also print the cost in euros at that rate

Questions mode (--qa): every question of the ID card bank (data/eval/qa/cie-questions.yaml:
answerable ones, the unanswerable and out-of-scope ones, the holdout reported apart) goes to
`run_turn` as a first message, and the reply is scored without a human:

- cited: at least one source, and every cited source is an expected source of the question
  or a saved page that contains one of its evidence quotes (unanswerable: the redirect, the
  related pages or a service's official page);
- evidence: the reply contains one of the evidence quotes, or a verified « » quote that
  shares at least 30 characters with one (the whole quote when shorter), or at least a
  verified « » quote of six words or more from an allowed source (another sentence of the
  right page); the report also counts the stricter "quote overlaps the evidence";
- honest (unanswerable and out of scope): the reply says the saved pages don't say it (a
  phrase per language, see DONT_KNOW) or is the safe fallback.

    python -m onevisit.evaluate --qa                       # real Claude: needs ANTHROPIC_API_KEY
    python -m onevisit.evaluate --qa --set holdout --limit 10 --transcripts /tmp/qa
    python -m onevisit.evaluate --qa --dry-run --out /tmp/qa.md   # no key, no network: a fake
                                                                   # client quotes the top passage

It refuses to run without a key (exit 2) unless --dry-run; the real run writes
docs/eval-results-qa.md, a dry run writes only where --out says.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import functools
import importlib.util
import itertools
import json
import os
import pathlib
import re
import sys
import time

from onevisit import agent, kb, validator

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "data" / "eval"
QA_DIR = EVAL_DIR / "qa"
QA_SERVICE = "carta-identita"
_QUESTION_SPLIT = re.compile(r"(?<=[.!?؟？])\s+|\n+")
# USD per million tokens: input, output, cache read, cache write (5-minute cache = 1.25 × input).
# Anthropic list prices; update them here when they change.
PRICES = {"claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50), "claude-haiku-4-5": (1.00, 5.00, 0.10, 1.25)}


def _scalar(raw: str) -> object:
    raw = raw.strip()
    if raw in ("null", "~", ""):
        return None
    if raw in ("true", "false"):
        return raw == "true"
    if raw.startswith("[") and raw.endswith("]"):
        return [_scalar(x) for x in re.split(r"\s*,\s*", raw[1:-1].strip()) if x.strip()]
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def load_yaml(text: str) -> dict:
    """The small YAML subset the scenarios use (PyYAML when installed, else this reader)."""
    try:
        import yaml  # type: ignore[import-untyped]  # optional: the app itself doesn't need it
        return yaml.safe_load(text)
    except ImportError:
        pass
    root: dict = {}
    stack: list[tuple[int, object]] = [(-1, root)]
    pending: tuple[int, dict, str] | None = None  # a "key:" waiting to see if a list or a mapping follows
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        if pending and indent > pending[0]:
            _, parent, key = pending
            parent[key] = [] if body.startswith("- ") else {}
            stack.append((pending[0], parent[key]))
        pending = None
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]
        if body.startswith("- ") and isinstance(container, list):
            container.append(_scalar(body[2:]))
            continue
        key, _, value = body.partition(":")
        if isinstance(container, dict):
            container[key.strip()] = _scalar(value) if value.strip() else None
            if not value.strip():
                pending = (indent, container, key.strip())
    return root


def scenarios(only: list[str] | None = None) -> list[dict]:
    out = [load_yaml(p.read_text(encoding="utf-8")) for p in sorted(EVAL_DIR.glob("*.yaml"))]
    return [s for s in out if not only or s["id"] in only]


@dataclasses.dataclass
class Result:
    scenario_id: str
    failures: list[str]
    turns: int
    blocked: int
    regenerated: int
    fallbacks: int
    tool_calls: int
    seconds: float
    transcript: list[dict]
    usage: dict = dataclasses.field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.failures

    def cost_usd(self, model: str) -> float | None:
        """List price of the scenario's tokens, or None for a model with no price here."""
        price = PRICES.get(model)
        if not price:
            return None
        u = self.usage
        tokens = (u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("cache_read_input_tokens", 0),
                  u.get("cache_creation_input_tokens", 0))
        return sum(t * p for t, p in zip(tokens, price)) / 1_000_000


def _asked(replies: list[str], phrase: str) -> bool:
    needle = validator.fold(phrase)
    return any(s.strip().endswith(("?", "؟", "？")) and needle in validator.fold(s)
               for r in replies for s in _QUESTION_SPLIT.split(r))


def _reply_lang(text: str) -> str | None:
    cleaned = re.sub(r"\[[^\]]*\]|\([^)]*\)|https?://\S+", " ", text)  # drop ids, Italian names, links
    return agent.guess_lang(cleaned)


def check(expect: dict, replies: list[str], trace: list[dict]) -> list[str]:
    """What failed against the scenario's expectations (empty list: passed)."""
    failures = []
    services = [s["input"].get("service_id") for s in trace if isinstance(s.get("input"), dict) and s["input"].get("service_id")]
    service = services[-1] if services else None
    if service != expect.get("service"):
        failures.append(f"service: expected {expect.get('service')}, got {service}")
    checklists = [s for s in trace if s.get("tool") == "get_checklist" and isinstance(s.get("output"), dict)]
    answers = (checklists[-1]["input"].get("answers") or {}) if checklists else {}
    variant = expect.get("variant")
    if variant and variant not in answers.values():
        failures.append(f"variant: expected {variant}, got {answers or None}")
    lang = expect.get("language")
    if lang and replies and _reply_lang(replies[-1]) not in (lang, None):
        failures.append(f"language: expected {lang}, got {_reply_lang(replies[-1])}")
    if expect.get("requirements_include"):
        have = {r["id"] for r in (checklists[-1]["output"].get("requirements", []) if checklists else [])}
        failures += [f"missing requirement: {r}" for r in expect["requirements_include"] if r not in have]
    text = validator.fold("\n".join(replies))
    failures += [f"forbidden phrase: {p}" for p in expect.get("forbidden_phrases") or []
                 if re.search(r"(?<!\w)" + re.escape(validator.fold(p)) + r"(?!\w)", text)]
    failures += [f"asked for: {p}" for p in expect.get("must_not_ask") or [] if _asked(replies, p)]
    wants_citations = expect["citations"] if "citations" in expect and expect["citations"] is not None \
        else expect.get("service") is not None
    known = set(kb.sources())
    if wants_citations and not any(validator.cited_source_ids(r, known) for r in replies):
        failures.append("no source cited")
    if expect.get("missing_procedure") and checklists:
        failures.append("out-of-catalogue request answered with a checklist")
    return failures


def run_one(scenario: dict, client, lang_hint: str = "en") -> Result:
    messages: list = []
    replies, trace, transcript = [], [], []
    blocked = regenerated = fallbacks = 0
    usage: dict = {}
    start = time.perf_counter()
    for text in scenario.get("messages") or []:
        messages.append({"role": "user", "content": text})
        reply = agent.run_turn(messages, client=client, lang=agent.guess_lang(text) or lang_hint)
        replies.append(reply["text"])
        trace += reply["trace"]
        for key, value in (reply.get("usage") or {}).items():
            usage[key] = usage.get(key, 0) + value
        check_info = reply.get("check") or {}
        blocked += int(bool(check_info.get("blocked")))
        regenerated += int(check_info.get("attempts", 1) > 1)
        fallbacks += int(bool(check_info.get("fallback")))
        transcript.append({"user": text, "assistant": reply["text"], "options": reply.get("options", []),
                           "tools": [{"tool": s["tool"], "input": s["input"]} for s in reply["trace"]],
                           "check": check_info, "cited": reply.get("cited", [])})
    seconds = time.perf_counter() - start
    return Result(scenario["id"], check(scenario.get("expect") or {}, replies, trace), len(replies), blocked,
                  regenerated, fallbacks, len(trace), seconds, transcript, usage)


def report(results: list[Result], model: str, usd_to_eur: float | None = None) -> str:
    passed = sum(r.passed for r in results)
    n = max(len(results), 1)
    turns = max(sum(r.turns for r in results), 1)

    def tot(field: str) -> int:
        return sum(r.usage.get(field, 0) for r in results)

    costs = [r.cost_usd(model) for r in results]
    known = [c for c in costs if c is not None]
    money = ""
    if known:
        per_case = sum(known) / len(known)
        eur = f" (≈ €{per_case * usd_to_eur:.3f} at {usd_to_eur} €/$)" if usd_to_eur else ""
        money = f" List-price cost per scenario: **${per_case:.3f}**{eur}; whole run ${sum(known):.2f}."
    lines = [
        "# Evaluation of the live agent (Streamlit app)",
        "",
        f"Model `{model}` · run on {dt.date.today().isoformat()} with `python -m onevisit.evaluate` · "
        f"**{passed}/{len(results)} scenarios passed**",
        "",
        f"Average per scenario: {sum(r.tool_calls for r in results) / n:.1f} tool calls, "
        f"{sum(r.seconds for r in results) / n:.1f} s. Replies blocked by the automatic check: "
        f"{sum(r.blocked for r in results)}; regenerated: {sum(r.regenerated for r in results)}; "
        f"replaced by the safe fallback: {sum(r.fallbacks for r in results)}.",
        "",
        f"Per citizen turn: {tot('requests') / turns:.1f} API requests, {sum(r.seconds for r in results) / turns:.1f} s, "
        f"{tot('input_tokens') / turns:,.0f} input tokens + {tot('cache_read_input_tokens') / turns:,.0f} read from the "
        f"prompt cache + {tot('cache_creation_input_tokens') / turns:,.0f} written to it, "
        f"{tot('output_tokens') / turns:,.0f} output tokens.{money}",
        "",
        "| Scenario | Result | Turns | Tool calls | Blocked | Regenerated | Fallback | Seconds | Tokens in / cached / out | Cost | Failed checks |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r, cost in zip(results, costs):
        u = r.usage
        tokens = (f"{u.get('input_tokens', 0):,} / {u.get('cache_read_input_tokens', 0):,} / "
                  f"{u.get('output_tokens', 0):,}")
        lines.append(f"| `{r.scenario_id}` | {'pass' if r.passed else 'FAIL'} | {r.turns} | {r.tool_calls} | {r.blocked} | "
                     f"{r.regenerated} | {r.fallbacks} | {r.seconds:.1f} | {tokens} | "
                     f"{'—' if cost is None else f'${cost:.3f}'} | {'; '.join(r.failures) or '—'} |")
    lines += ["", "Scenarios: [`data/eval/`](../data/eval/). Checks: service, the answer that defines the case, "
              "language of the last reply, required checklist items, forbidden phrases, questions never to ask, "
              "at least one cited source (none for out-of-catalogue requests). Tokens come from `response.usage`; "
              "the cost uses the list prices in `onevisit/evaluate.py` (`PRICES`)."]
    return "\n".join(lines) + "\n"


# ---------- questions mode: the ID card question bank through the live agent ----------

# "The saved pages don't say it", per language, folded like validator.fold (lower case, no
# accents, bare Arabic letters). A substring of the folded reply is enough.
# The don't-know phrases live with the validator (it also requires them, or a verbatim quote, in an
# answer from the pages); the Spanish reflexive "no se puede" is not one.
DONT_KNOW = validator.DONT_KNOW


def says_dont_know(text: str) -> bool:
    """The reply says the saved official pages don't answer (any language of DONT_KNOW)."""
    return validator.says_dont_know(text)


@functools.lru_cache(maxsize=1)
def _check_bank():
    """data/eval/qa/check_bank.py, the bank's own loader and page reader (not a package)."""
    spec = importlib.util.spec_from_file_location("onevisit_qa_check_bank", QA_DIR / "check_bank.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QA_SETS = ("all", "tuning", "holdout", "honesty")


def qa_questions(only: list[str] | None = None, which: str = "all", limit: int | None = None) -> list[dict]:
    """Questions of the ID card bank: all, tuning (answerable, not holdout), holdout, or
    honesty (unanswerable and out of scope); `only` keeps those ids; `limit` the first n."""
    bank = _check_bank().load_bank(QA_DIR / "cie-questions.yaml")["questions"]
    keep = {
        "all": lambda q: True,
        "tuning": lambda q: q["answerable"] and not q.get("holdout"),
        "holdout": lambda q: bool(q.get("holdout")),
        "honesty": lambda q: not q["answerable"],
    }[which]
    out = [q for q in bank if keep(q) and (not only or q["id"] in only)]
    return out[:limit] if limit else out


@functools.lru_cache(maxsize=4096)
def _holders(quote: str) -> frozenset[str]:
    """Saved pages whose text contains this evidence quote (a duplicate FAQ page holds it too)."""
    cb = _check_bank()
    needle = cb.norm(quote)
    return frozenset(sid for sid in kb.sources() if needle and needle in (cb.page_text(sid) or ""))


def allowed_sources(question: dict) -> set[str]:
    """Sources a reply to this question may cite."""
    if question["answerable"]:
        allowed = set(question.get("expected_sources") or [])
        for ev in question.get("evidence") or []:
            allowed |= _holders(ev["quote"])
        return allowed
    allowed = set(question.get("related_sources") or [])
    if (question.get("redirect") or {}).get("source"):
        allowed.add(question["redirect"]["source"])
    allowed |= {page["source_id"] for s in kb.list_services()
                if (page := kb.service_links(s["id"]).get("official_url"))}
    return allowed


@dataclasses.dataclass
class QAResult:
    question_id: str
    lang: str
    facet: str
    answerable: bool
    holdout: bool
    failures: list[str]
    cited: list[str]
    quotes: list[dict]
    seconds: float
    tool_calls: int
    blocked: bool
    fallback: bool
    text: str
    tools: list[dict]
    usage: dict = dataclasses.field(default_factory=dict)
    overlap: bool = False  # a quote or the text holds one of the question's evidence quotes

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def group(self) -> str:
        if not self.answerable:
            return "honesty"
        return "holdout" if self.holdout else "tuning"


MIN_OVERLAP = 30  # characters a quote must share with an evidence quote (as run_retrieval.py)
MIN_QUOTE_WORDS = 6  # a verified quote this long from an allowed source counts as evidence


def _shares(a: str, b: str, need: int) -> bool:
    """a and b (normalised) have a common stretch of at least `need` characters."""
    import difflib

    match = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return match.size >= need


def evidence_overlap(question: dict, reply: dict) -> bool:
    """The reply holds the question's evidence: an evidence quote word for word, or a verified
    « » quote sharing MIN_OVERLAP characters with one (the whole evidence quote if shorter)."""
    folded = validator.normalize_quote(reply.get("text") or "")
    for ev in question.get("evidence") or []:
        needle = validator.normalize_quote(ev["quote"]).strip(" .")
        if needle and needle in folded:
            return True
        for q in reply.get("quotes") or []:
            quote = validator.normalize_quote(q["text"])
            if _shares(quote, needle, min(MIN_OVERLAP, len(needle))):
                return True
    return False


def check_qa(question: dict, reply: dict) -> list[str]:
    """What failed for one question (empty list: passed)."""
    failures = []
    text, cited = reply["text"], reply.get("cited") or []
    fallback = bool((reply.get("check") or {}).get("fallback"))
    allowed = allowed_sources(question)
    outside = [c for c in cited if c not in allowed]
    if outside:
        failures.append("cited outside the expected sources: " + ", ".join(outside))
    if question["answerable"]:
        if fallback:
            failures.append("safe fallback instead of an answer")
        if not cited:
            failures.append("no source cited")
        quoted = any(q["source_id"] in allowed and len(q["text"].split()) >= MIN_QUOTE_WORDS
                     for q in reply.get("quotes") or [])
        if not (quoted or evidence_overlap(question, reply)):
            failures.append("no evidence: no verified quote of an expected source")
    elif not (fallback or says_dont_know(text)):
        failures.append("does not say the saved pages don't answer")
    return failures


def run_qa_one(question: dict, client) -> QAResult:
    """One question of the bank as the first message of a conversation."""
    messages: list = [{"role": "user", "content": question["question"]}]
    start = time.perf_counter()
    reply = agent.run_turn(messages, client=client, lang=question.get("lang") or "en")
    seconds = time.perf_counter() - start
    info = reply.get("check") or {}
    return QAResult(question["id"], question.get("lang", ""), question.get("facet", ""), bool(question["answerable"]),
                    bool(question.get("holdout")), check_qa(question, reply), reply.get("cited") or [],
                    reply.get("quotes") or [], seconds, len(reply["trace"]), bool(info.get("blocked")),
                    bool(info.get("fallback")), reply["text"],
                    [{"tool": s["tool"], "input": s["input"]} for s in reply["trace"]], reply.get("usage") or {},
                    bool(question["answerable"]) and evidence_overlap(question, reply))


def _rate(results: list[QAResult]) -> str:
    return f"{sum(r.passed for r in results)}/{len(results)}" if results else "—"


def qa_report(results: list[QAResult], model: str, dry_run: bool = False) -> str:
    """Markdown report of a questions run: groups, languages, failures, tokens."""
    groups = {g: [r for r in results if r.group == g] for g in ("tuning", "holdout", "honesty")}
    answerable = [r for r in results if r.answerable]
    turns = max(len(results), 1)
    tokens = {f: sum(r.usage.get(f, 0) for r in results) for f in agent.USAGE_FIELDS}
    title = "# Questions on the ID card: the live agent against the question bank"
    mode = ("**Dry run**: a fake client (no Claude, no network) searches the question and quotes the first "
            "sentence of the top passage when the search is confident, else says the pages don't answer. It "
            "measures the pipeline (tools, automatic check, scoring), not Claude."
            if dry_run else f"Model `{model}`, through `onevisit.agent.run_turn` (the app's own loop).")
    lines = [
        title, "",
        f"{mode} Run on {dt.date.today().isoformat()} with `python -m onevisit.evaluate --qa"
        f"{' --dry-run' if dry_run else ''}` · **{sum(r.passed for r in results)}/{len(results)} questions passed**",
        "",
        "| Set | Passed | Cited only expected sources | Verified quote or evidence | Quote overlaps the evidence | "
        "Says it doesn't know | Blocked once | Fallback |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, rs in groups.items():
        if not rs:
            continue
        cited_ok = sum(not any(f.startswith(("cited outside", "no source")) for f in r.failures) for r in rs)
        evidence = sum(not any(f.startswith("no evidence") for f in r.failures) for r in rs) if name != "honesty" else None
        honest = sum(not any(f.startswith("does not say") for f in r.failures) for r in rs) if name == "honesty" else None
        overlap = f"{sum(r.overlap for r in rs)}/{len(rs)}" if name != "honesty" else "—"
        lines.append(f"| {name} | {_rate(rs)} | {cited_ok}/{len(rs)} | "
                     f"{'—' if evidence is None else f'{evidence}/{len(rs)}'} | {overlap} | "
                     f"{'—' if honest is None else f'{honest}/{len(rs)}'} | {sum(r.blocked for r in rs)} | "
                     f"{sum(r.fallback for r in rs)} |")
    by_lang: dict[str, list[QAResult]] = {}
    for r in results:
        by_lang.setdefault(r.lang, []).append(r)
    lines += ["", "By language: " + " · ".join(f"{lang} {_rate(rs)}" for lang, rs in sorted(by_lang.items())), "",
              f"Per question: {sum(r.tool_calls for r in results) / turns:.1f} tool calls, "
              f"{sum(r.seconds for r in results) / turns:.1f} s, {tokens['input_tokens'] / turns:,.0f} input tokens + "
              f"{tokens['cache_read_input_tokens'] / turns:,.0f} read from the prompt cache, "
              f"{tokens['output_tokens'] / turns:,.0f} output tokens. Answerable questions with a verified « » quote: "
              f"{sum(bool(r.quotes) for r in answerable)}/{len(answerable)}.", ""]
    failed = [r for r in results if not r.passed]
    if failed:
        lines += ["## Failed questions", "", "| Question | Set | Lang | Cited | Failed checks |", "|---|---|---|---|---|"]
        lines += [f"| `{r.question_id}` | {r.group} | {r.lang} | {', '.join(r.cited) or '—'} | "
                  f"{'; '.join(r.failures)} |" for r in failed]
        lines.append("")
    lines += ["Bank: [`data/eval/qa/cie-questions.yaml`](../data/eval/qa/cie-questions.yaml). Checks: cited sources "
              "⊆ expected sources ∪ pages holding an evidence quote (unanswerable: redirect, related pages, official "
              "pages); evidence = an evidence quote in the reply, a verified « » quote sharing 30 characters with "
              "one, or a verified « » quote of six words or more from an allowed source; "
              "unanswerable and out of scope = the reply says the saved pages don't answer (or the safe fallback). "
              "Whether a reply to an unanswerable question states no rule needs a human: see the transcripts."]
    return "\n".join(lines) + "\n"


# ---------- dry run: a fake client, no key, no network ----------

@dataclasses.dataclass
class _Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class _Response:
    content: list
    stop_reason: str = "end_turn"
    usage: object = None


_SENTENCE_END = re.compile(r"(?<=[.;:!?])\s|\n\s*\n")


def _first_sentence(text: str, limit: int = 300, min_words: int = MIN_QUOTE_WORDS) -> str:
    """A verbatim slice of a passage: its first sentence of at least `min_words` words (else the
    first one), at most `limit` characters, without guillemets."""
    text = text.split("«")[0].split("»")[0].strip()
    pieces, at = [], 0
    for end in _SENTENCE_END.finditer(text):
        pieces.append(text[at:end.start()])
        at = end.end()
    pieces.append(text[at:])
    pieces = [p.strip() for p in pieces if p.strip()]
    cut = next((p for p in pieces if len(p.split()) >= min_words), pieces[0] if pieces else "")
    if len(cut) > limit:
        cut = cut[:limit].rsplit(" ", 1)[0]
    return cut.strip()


class DryRunClient:
    """Plays Claude without the network: searches the question, then quotes the first sentence of
    the top passage when the search is confident, else says the saved pages don't answer and
    links the official page. client.beta.messages.create(...) as in the SDK."""

    def __init__(self, service_id: str = QA_SERVICE) -> None:
        self.service_id = service_id
        self.beta = self
        self.messages = self
        self._ids = itertools.count(1)

    def create(self, **kwargs) -> _Response:
        messages = kwargs["messages"]
        last = messages[-1]["content"]
        if isinstance(last, str) and not last.startswith("AUTOMATIC CHECK"):
            return _Response([_Block("tool_use", id=f"toolu_dry_{next(self._ids)}", name="search_official_pages",
                                     input={"query": last, "service_id": self.service_id})], stop_reason="tool_use")
        payload: dict = {}
        for m in reversed(messages):
            if isinstance(m.get("content"), list) and m["content"] and isinstance(m["content"][0], dict) \
                    and m["content"][0].get("type") == "tool_result":
                payload = json.loads(m["content"][0]["content"])
                break
        results = payload.get("results") or []
        page = payload.get("official_page") or {}
        if isinstance(last, list) and results and payload.get("confident"):
            top = results[0]
            return _Response([_Block("text", text=f"«{_first_sentence(top['text'])}» [{top['source_id']}]")])
        cite = f" [{page['source_id']}]" if page else ""
        return _Response([_Block("text", text="Le pagine ufficiali salvate non lo dicono. Pagina ufficiale: "
                                              f"{page.get('url') or agent.OFFICIAL_HOME}{cite}")])


def has_key() -> bool:
    """A key that can work: not empty and not the .env.example placeholder ("sk-ant-...")."""
    value = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    return len(value) >= 30 and "..." not in value


def main_qa(args: argparse.Namespace) -> int:
    """--qa: the question bank through run_turn; real Claude, or the dry-run client."""
    if args.dry_run:
        client = DryRunClient()
    elif not has_key():
        print("No ANTHROPIC_API_KEY: the questions run calls Claude. Use --dry-run to test the pipeline "
              "without a key.", file=sys.stderr)
        return 2
    else:
        import anthropic

        client = anthropic.Anthropic()
    questions = qa_questions(args.only, args.set, args.limit)
    results = [run_qa_one(q, client) for q in questions]
    md = qa_report(results, agent.MODEL, dry_run=args.dry_run)
    out = args.out or (None if args.dry_run else str(ROOT / "docs" / "eval-results-qa.md"))
    if out:
        pathlib.Path(out).write_text(md, encoding="utf-8")
    if args.transcripts:
        folder = pathlib.Path(args.transcripts)
        folder.mkdir(parents=True, exist_ok=True)
        for r in results:
            (folder / f"{r.question_id}.json").write_text(
                json.dumps(dataclasses.asdict(r), ensure_ascii=False, indent=1), encoding="utf-8")
    print(md)
    return 0 if all(r.passed for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run data/eval against the live agent (needs a key).")
    ap.add_argument("--only", nargs="*", help="scenario ids (with --qa: question ids)")
    ap.add_argument("--out", help="report file (default docs/eval-results.md; --qa: docs/eval-results-qa.md)")
    ap.add_argument("--transcripts", help="folder for one JSON transcript per scenario or question")
    ap.add_argument("--usd-to-eur", type=float, help="exchange rate to also show the cost in euros")
    ap.add_argument("--qa", action="store_true", help="run the ID card question bank (data/eval/qa)")
    ap.add_argument("--set", choices=QA_SETS, default="all", help="--qa: which questions (holdout reported apart)")
    ap.add_argument("--limit", type=int, help="--qa: only the first n questions")
    ap.add_argument("--dry-run", action="store_true", help="--qa: a fake client instead of Claude (no key needed)")
    args = ap.parse_args(argv)
    if args.qa:
        return main_qa(args)
    if not has_key():
        print("No ANTHROPIC_API_KEY: the scenarios call Claude.", file=sys.stderr)
        return 2
    import anthropic

    client = anthropic.Anthropic()
    results = [run_one(s, client) for s in scenarios(args.only)]
    args.out = args.out or str(ROOT / "docs" / "eval-results.md")
    pathlib.Path(args.out).write_text(report(results, agent.MODEL, args.usd_to_eur), encoding="utf-8")
    if args.transcripts:
        folder = pathlib.Path(args.transcripts)
        folder.mkdir(parents=True, exist_ok=True)
        for r in results:
            (folder / f"{r.scenario_id}.json").write_text(json.dumps(r.transcript, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
    print(report(results, agent.MODEL, args.usd_to_eur))
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
