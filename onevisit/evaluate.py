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
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import pathlib
import re
import sys
import time

from onevisit import agent, kb, validator

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "data" / "eval"
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run data/eval against the live agent (needs a key).")
    ap.add_argument("--only", nargs="*", help="scenario ids")
    ap.add_argument("--out", default=str(ROOT / "docs" / "eval-results.md"))
    ap.add_argument("--transcripts", help="folder for one JSON transcript per scenario")
    ap.add_argument("--usd-to-eur", type=float, help="exchange rate to also show the cost in euros")
    args = ap.parse_args(argv)
    import anthropic

    client = anthropic.Anthropic()
    results = [run_one(s, client) for s in scenarios(args.only)]
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
