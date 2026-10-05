"""Measure the replay's answers to ID card questions (no model, no API key) on the question bank.

    python data/eval/qa/run_demo_qa.py                         # Markdown on stdout
    python data/eval/qa/run_demo_qa.py --out data/eval/qa/RESULTS.md
    python data/eval/qa/run_demo_qa.py --json

Without a key the app answers a typed message with onevisit.demo.respond: keyword rules decide
whether it is a question, a new case or an answer, and a question is answered with the passages
the keyword search ranks first, quoted verbatim as cards. Every bank question goes through that
same function three ways:

- typed: the first message of a conversation, demo.respond(None, question, lang), as the page
  does when someone types it on the first screen;
- mid-case: typed while a case is open (the lost-ID persona "cie-isola", its first deciding
  question pending), demo.respond(state, question, lang);
- asked: demo.ask, the path of the example-question chips, which always treats the message as a
  question (it isolates the search from the question-or-case rules).

A reply is scored on what the page shows:

- hit: a quote card shown as the answer (search reason "ok") comes from one of the question's
  expected sources (or a page holding the same evidence quote) and shares 30 characters with an
  evidence quote (the whole quote when shorter), as run_retrieval.py counts a hit;
- right-page: a card shown as the answer comes from an expected page, but its quote (cut to
  about 450 characters) doesn't hold the evidence: it may sit behind "Leggi tutto il passaggio";
- closest: the reply says the pages don't answer with certainty and the evidence is among the
  closest passages it shows after that line;
- wrong-confident: the reply presents passages as the answer and none comes from an expected page;
  for an unanswerable question, any reply that presents passages as the answer;
- honest: the reply says the saved pages don't answer and links the official page, and shows no
  card with the evidence (for unanswerable questions this is the right reply);
- case: the message opened a case (or was read as an answer to the case) and no quote answers it;
- unclear: the replay said it couldn't read the message.

The bank's expected sources may miss a page that also answers: a "wrong-confident" reply can
still be right. The report lists those replies with the page and section quoted so a person can
check them. The live path (Claude with the same tools) is measured with
`python -m onevisit.evaluate --qa` when an API key is set.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import pathlib
import re
import sys
import time
from collections import Counter
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _path in (str(ROOT), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import check_bank  # noqa: E402  # the bank's loader lives next to this file
import run_retrieval  # noqa: E402  # the search-only numbers, for comparison

from onevisit import demo, evaluate, validator  # noqa: E402  # the replay under test
from onevisit.agent import guess_lang  # noqa: E402

PERSONA = "cie-isola"  # lost ID card: the case a question interrupts in "mid-case"
MODES = ("typed", "mid-case", "asked")
OUTCOMES = ("hit", "right-page", "closest", "wrong-confident", "honest", "case", "unclear")
MIN_OVERLAP = 30  # characters a card must share with an evidence quote (as run_retrieval.py)
# What follows this line in the --out file is written by hand (a person's reading of the replies):
# rewriting the report keeps it.
NOTES_MARK = "<!-- Notes written by hand below this line: run_demo_qa.py --out keeps them. -->"


def page_language(question: str) -> str:
    """The page language when the message is sent, as the app's follow_language sets it: the
    language of the message when the replay writes it (12 characters or more), else Italian."""
    if "¿" in question or "¡" in question:
        return "es"
    guessed = guess_lang(question) if len(question) >= 12 else None
    return guessed if guessed in demo.LANGS else "it"


def _norm(text: str) -> str:
    return validator.normalize_quote(text or "").strip(" .…")


def _shares(card: str, quote: str) -> bool:
    need = min(MIN_OVERLAP, len(quote))
    if not need:
        return False
    if quote in card:
        return True
    match = difflib.SequenceMatcher(None, card, quote, autojunk=False).find_longest_match(
        0, len(card), 0, len(quote)
    )
    return match.size >= need


def right_page(question: dict[str, Any], card: dict[str, Any]) -> bool:
    """The card comes from an expected page (or one holding the same evidence quote)."""
    return card.get("source_id") in evaluate.allowed_sources(question)


def card_holds_evidence(question: dict[str, Any], card: dict[str, Any]) -> bool:
    """The card comes from a page allowed for this question and shares an evidence quote."""
    if not right_page(question, card):
        return False
    text = _norm(card.get("text", ""))
    return any(_shares(text, _norm(ev["quote"])) for ev in question.get("evidence") or [])


def shown_cards(reply: dict[str, Any]) -> list[dict[str, Any]]:
    """The quote cards the page shows: the replay's cards whose « » quote is in the reply text."""
    text = reply.get("text") or ""
    cards = (reply.get("qa") or {}).get("cards") or []
    return [c for c in cards if f"«{c.get('text', '')}»" in text]


def _plain(text: str) -> str:
    """A quote as one line for the report: images dropped, links as their text."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text or "")
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return " ".join(text.split())


def outcome(question: dict[str, Any], reply: dict[str, Any], kind: str) -> str:
    """One of OUTCOMES for this reply (see the module docstring)."""
    qa = reply.get("qa")
    if not qa:
        return "unclear" if kind == "unclear" else "case"
    cards = shown_cards(reply)
    reason = qa.get("reason")
    if not question["answerable"]:
        if reason == "ok" and cards:
            return "wrong-confident"
        return "honest" if reason != "ok" else "case"
    holds = any(card_holds_evidence(question, c) for c in cards)
    if reason == "ok" and cards:
        if holds:
            return "hit"
        return "right-page" if any(right_page(question, c) for c in cards) else "wrong-confident"
    if reason == "ok":  # a case-opening message whose question found nothing to quote
        return "case"
    return "closest" if holds else "honest"


def _persona_state(lang: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if lang not in cache:
        state, _, _ = demo.start_persona(PERSONA, lang)
        cache[lang] = state
    return copy.deepcopy(cache[lang])


def run_question(q: dict[str, Any], personas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The three replies to one bank question and how each scores."""
    lang = page_language(q["question"])
    row: dict[str, Any] = {
        "id": q["id"],
        "lang": q["lang"],
        "facet": q["facet"],
        "holdout": bool(q.get("holdout")),
        "answerable": bool(q["answerable"]),
        "question": q["question"],
        "modes": {},
    }
    for mode in MODES:
        if mode == "typed":
            kind = demo.classify(None, q["question"])
            _, reply = demo.respond(None, q["question"], lang)
        elif mode == "mid-case":
            state = _persona_state(lang, personas)
            kind = demo.classify(state, q["question"])
            _, reply = demo.respond(state, q["question"], lang)
        else:
            state = demo.new_state(None, lang, persona=None, routing="keywords")
            kind = "question"
            reply = demo.ask(state, q["question"], lang)
        cards = shown_cards(reply)
        row["modes"][mode] = {
            "kind": kind,
            "reason": (reply.get("qa") or {}).get("reason"),
            "outcome": outcome(q, reply, kind),
            "blocked": list((reply.get("check") or {}).get("blocked") or []),
            "cards": [
                {"source_id": c["source_id"], "start": _plain(c.get("text", ""))[:90]}
                for c in cards
            ],
        }
    return row


def _group(row: dict[str, Any]) -> str:
    if not row["answerable"]:
        return "honesty"
    return "holdout" if row["holdout"] else "tuning"


def summarise(rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    """Counts of each outcome, and the rates the report leads with."""
    counts = Counter(r["modes"][mode]["outcome"] for r in rows)
    n = len(rows)
    out: dict[str, Any] = {"n": n, **{o: counts.get(o, 0) for o in OUTCOMES}}
    out["blocked"] = sum(bool(r["modes"][mode]["blocked"]) for r in rows)
    out["hit_rate"] = round(counts.get("hit", 0) / n, 3) if n else 0.0
    out["wrong_confident_rate"] = round(counts.get("wrong-confident", 0) / n, 3) if n else 0.0
    out["honest_rate"] = round(counts.get("honest", 0) / n, 3) if n else 0.0
    return out


def measure(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Run every question in every mode; numbers per mode and group (tuning, holdout, honesty)."""
    personas: dict[str, dict[str, Any]] = {}
    start = time.perf_counter()
    rows = [run_question(q, personas) for q in questions]
    report: dict[str, Any] = {
        "seconds": round(time.perf_counter() - start, 1),
        "rows": rows,
        "groups": {},
    }
    for mode in MODES:
        for group in ("tuning", "holdout", "honesty"):
            part = [r for r in rows if _group(r) == group]
            if part:
                report["groups"][f"{mode}/{group}"] = summarise(part, mode)
        for group in ("tuning", "holdout"):
            for split, test in (("it-en", True), ("other", False)):
                part = [
                    r
                    for r in rows
                    if _group(r) == group and (r["lang"] in run_retrieval.MAIN_LANGS) == test
                ]
                if part:
                    report["groups"][f"{mode}/{group}/{split}"] = summarise(part, mode)
    return report


# ---------------------------------------------------------------- output


def _pct(part: int, n: int) -> str:
    return f"{part}/{n} ({100 * part / n:.0f}%)" if n else "—"


def markdown(report: dict[str, Any], retrieval: dict[str, Any] | None) -> str:
    """RESULTS.md: what the replay shows for each kind of question, holdout apart."""
    groups = report["groups"]
    lines = [
        "# The replay's answers to ID card questions: results",
        "",
        "Generated by `python data/eval/qa/run_demo_qa.py --out data/eval/qa/RESULTS.md` on the",
        f"question bank `cie-questions.yaml` ({len(report['rows'])} questions). No model and no",
        "API key: this measures the replay (`onevisit/demo.py`, keyword rules plus the keyword",
        "search of the saved official pages), the answers a visitor gets on `?demo=1` or when no",
        "key is set. The live path, Claude with the same tools, is measured with",
        "`python -m onevisit.evaluate --qa` when a key is set (not run here: no key in this",
        "sandbox).",
        "",
        "How each reply is scored (details in the script's docstring):",
        "",
        "- **hit**: a quote card shown as the answer comes from an expected page and holds the",
        "  question's evidence (30 characters of an evidence quote, as `run_retrieval.py`);",
        "- **right page**: a card shown as the answer comes from an expected page, but the quote",
        "  (cut to about 450 characters) doesn't hold the evidence; the card's \"Leggi tutto il",
        '  passaggio" may;',
        "- **closest**: the reply says the pages don't answer with certainty, then shows the",
        "  evidence among the closest passages;",
        "- **wrong-confident**: the reply presents passages as the answer and none comes from an",
        "  expected page (for an unanswerable question: any passages presented as the answer);",
        "- **honest**: the reply says the saved pages don't answer and links the official page;",
        "- **case**: the message was read as a new case or an answer to the open case, and no",
        "  quote answers the question;",
        "- **unclear**: the replay said it couldn't read the message.",
        "",
        "Three ways in: **typed** (first message, `demo.respond(None, …)`), **mid-case** (typed",
        "while the lost-ID case waits for its first answer) and **asked** (`demo.ask`, the",
        "example-question chips: always a question, so it isolates the search).",
        "",
        "## Answerable questions",
        "",
        "| way in | set | n | hit | right page | closest | wrong-confident | honest | case "
        "| unclear |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        for group in ("tuning", "holdout"):
            g = groups.get(f"{mode}/{group}")
            if not g:
                continue
            lines.append(
                f"| {mode} | {group} | {g['n']} | {_pct(g['hit'], g['n'])} | {g['right-page']} | "
                f"{g['closest']} | {g['wrong-confident']} | {g['honest']} | {g['case']} | "
                f"{g['unclear']} |"
            )
    lines += [
        "",
        "By language (hit rate, typed):",
        "",
        "| set | it/en | other languages |",
        "|---|---:|---:|",
    ]
    for group in ("tuning", "holdout"):
        a = groups.get(f"typed/{group}/it-en") or {}
        b = groups.get(f"typed/{group}/other") or {}
        lines.append(
            f"| {group} | {_pct(a.get('hit', 0), a.get('n', 0))} | "
            f"{_pct(b.get('hit', 0), b.get('n', 0))} |"
        )
    lines += [
        "",
        "## Unanswerable and out of scope",
        "",
        "| way in | n | honest (right) | wrong-confident | case | unclear |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        g = groups.get(f"{mode}/honesty")
        if g:
            lines.append(
                f"| {mode} | {g['n']} | {_pct(g['honest'], g['n'])} | {g['wrong-confident']} | "
                f"{g['case']} | {g['unclear']} |"
            )
    blocked = sum(g["blocked"] for k, g in groups.items() if k.count("/") == 1)
    lines += [
        "",
        f"Replies the validator blocked (every reply is checked, quotes against the passages "
        f"the search returned): {blocked}.",
    ]
    if retrieval:
        rg = retrieval["groups"]
        lines += [
            "",
            "## For comparison: the search alone",
            "",
            "`run_retrieval.py --holdout`: an expected passage among the top k results.",
            "",
            "| set | n | hit@1 | hit@3 | hit@5 |",
            "|---|---:|---:|---:|---:|",
        ]
        for name in ("tuning/all", "holdout/all"):
            g = rg.get(name) or {}
            if g:
                lines.append(
                    f"| {name.split('/')[0]} | {g['n']} | {g['hit@1']:.3f} | {g['hit@3']:.3f} | "
                    f"{g['hit@5']:.3f} |"
                )
        u = retrieval.get("unanswerable") or {}
        if "confident" in u:
            lines.append("")
            lines.append(
                f"Unanswerable questions whose top passage the search marks confident: "
                f"{u['confident']:.3f} ({u['n']} questions)."
            )
    lines += _lists(report)
    return "\n".join(lines) + "\n"


def _lists(report: dict[str, Any]) -> list[str]:
    rows = report["rows"]
    out: list[str] = []

    def line(r: dict[str, Any], mode: str) -> str:
        m = r["modes"][mode]
        cards = "; ".join(f"[{c['source_id']}] «{c['start']}…»" for c in m["cards"]) or "no card"
        return f"- {r['id']} ({r['lang']}): {r['question']}  \n  {m['outcome']}: {cards}"

    for group, title in (
        ("holdout", "Holdout questions without a hit (typed)"),
        ("tuning", "Tuning questions without a hit (typed)"),
    ):
        miss = [r for r in rows if _group(r) == group and r["modes"]["typed"]["outcome"] != "hit"]
        out += ["", f"## {title}: {len(miss)}", ""]
        out += [line(r, "typed") for r in miss]
    wrong = [r for r in rows if r["modes"]["typed"]["outcome"] == "wrong-confident"]
    out += [
        "",
        f"## Wrong-confident replies (typed): {len(wrong)}",
        "",
        "Passages presented as the answer without the bank's evidence. Some may still answer",
        "(the bank lists the pages its author found); each needs a person's look.",
        "",
    ]
    out += [line(r, "typed") for r in wrong]
    flips = [
        r
        for r in rows
        if r["answerable"]
        and r["modes"]["asked"]["outcome"] == "hit"
        and r["modes"]["typed"]["outcome"] != "hit"
    ]
    out += [
        "",
        f"## Lost by the question-or-case rules: {len(flips)}",
        "",
        "Hits when asked through the chips' path, not when typed (read as a case or an answer):",
        "",
    ]
    out += [
        f"- {r['id']} ({r['lang']}): {r['question']} -> {r['modes']['typed']['kind']}"
        for r in flips
    ]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print the numbers as JSON")
    ap.add_argument("--out", type=pathlib.Path, default=None, help="write the Markdown report")
    ap.add_argument("--only", nargs="*", default=None, help="question ids to run")
    args = ap.parse_args(argv)
    bank = check_bank.load_bank()["questions"]
    questions = [q for q in bank if not args.only or q["id"] in args.only]
    report = measure(questions)
    retrieval = None if args.only else run_retrieval.measure(bank)
    text = markdown(report, retrieval)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        old = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        notes = old[old.index(NOTES_MARK) :] if NOTES_MARK in old else ""
        args.out.write_text(text + ("\n" + notes if notes else ""), encoding="utf-8")
    if args.json:
        slim = {key: value for key, value in report.items() if key != "rows"}
        sys.stdout.write(json.dumps(slim, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
