"""Measure the passage search (onevisit/search.py) on the ID card question bank.

    python data/eval/qa/run_retrieval.py              # tuning set only, holdout not run
    python data/eval/qa/run_retrieval.py --holdout    # also the holdout, reported apart
    python data/eval/qa/run_retrieval.py --json       # numbers as JSON instead of a summary
    python data/eval/qa/run_retrieval.py --out report.md

Every question runs search(question, service_id="carta-identita", k=5). A result is a hit
when it comes from one of the question's expected sources AND its passage contains, or
overlaps, an evidence quote of that source (the right page and the right part of it).
"Page hit" counts the source alone. Unanswerable and out-of-scope questions have no hit:
for them the report gives the score distribution and how often the search still claims a
confident match, to calibrate the "no good match" threshold.

Groups: answerable Italian and English, answerable in the other languages (es, fr, ar, zh,
uk, bn: the replay demo searches in the user's words; live Claude can also search in
Italian), and unanswerable. Holdout questions are only run with --holdout, and their
failures are listed apart: don't tune on them.

Standard library only (plus the bank's own loader); runs under the app's Python 3.11 venv.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _path in (str(ROOT), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import check_bank  # noqa: E402  # the bank's loader lives next to this file

from onevisit import search  # noqa: E402  # the module under test, from the repo root

SERVICE = "carta-identita"
K = 5
MIN_OVERLAP = 30  # characters of a quote a passage must share, or the whole quote if shorter
MAIN_LANGS = ("it", "en")


# ---------------------------------------------------------------- matching passages to quotes


def _spans(haystack: str, needle: str) -> list[tuple[int, int]]:
    """Every (start, end) where needle occurs in haystack."""
    out: list[tuple[int, int]] = []
    if not needle:
        return out
    start = haystack.find(needle)
    while start >= 0:
        out.append((start, start + len(needle)))
        start = haystack.find(needle, start + 1)
    return out


def passage_covers(source_id: str, passage: str, quotes: Iterable[str]) -> bool:
    """True when the passage contains, or overlaps by MIN_OVERLAP characters, one quote.

    Both are located in the normalised page body (check_bank.norm: spacing and typographic
    quotes), so a quote cut in two by a passage boundary still counts for each half."""
    body = check_bank.page_text(source_id)
    if body is None:
        return False
    p_spans = _spans(body, check_bank.norm(passage))
    for quote in quotes:
        q = check_bank.norm(quote)
        need = min(MIN_OVERLAP, len(q))
        for qa, qb in _spans(body, q):
            for pa, pb in p_spans:
                if min(qb, pb) - max(qa, pa) >= need:
                    return True
    return False


# ---------------------------------------------------------------- one question


def _confidence(results: list[dict[str, Any]]) -> tuple[bool | None, float | None]:
    """Whether the search says its top result answers (None when the module doesn't say)."""
    if not results:
        return False, 0.0
    top = results[0]
    confident = top.get("confident")
    value = top.get("confidence")
    return (
        None if confident is None else bool(confident),
        None if value is None else float(value),
    )


def run_question(q: dict[str, Any], k: int = K) -> dict[str, Any]:
    """Search one bank question; ranks (1-based) of the first strict and page hits."""
    results = search.search(q["question"], service_id=SERVICE, k=k)
    expected = set(q.get("expected_sources") or [])
    quotes: dict[str, list[str]] = defaultdict(list)
    for item in q.get("evidence") or []:
        quotes[item["source"]].append(item["quote"])
    strict = page = None
    for rank, r in enumerate(results, 1):
        if r["source_id"] not in expected:
            continue
        page = page or rank
        if strict is None and passage_covers(r["source_id"], r["text"], quotes[r["source_id"]]):
            strict = rank
    confident, confidence = _confidence(results)
    return {
        "id": q["id"],
        "lang": q["lang"],
        "facet": q["facet"],
        "holdout": bool(q.get("holdout")),
        "answerable": bool(q.get("answerable")),
        "question": q["question"],
        "expected": sorted(expected),
        "found": [r["source_id"] for r in results],
        "headings": [r.get("heading", "") for r in results],
        "top_score": results[0]["score"] if results else 0.0,
        "confident": confident,
        "confidence": confidence,
        "strict_rank": strict,
        "page_rank": page,
    }


# ---------------------------------------------------------------- aggregates


def _rate(rows: list[dict[str, Any]], test: Callable[[dict[str, Any]], bool]) -> float:
    return round(sum(map(test, rows)) / len(rows), 3) if rows else 0.0


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """hit@1/3/5 (strict and page-only) for answerable rows; confidence rates when known."""
    out: dict[str, Any] = {"n": len(rows)}
    for n in (1, 3, 5):
        out[f"hit@{n}"] = _rate(rows, lambda r, n=n: (r["strict_rank"] or 99) <= n)
        out[f"page@{n}"] = _rate(rows, lambda r, n=n: (r["page_rank"] or 99) <= n)
    known = [r for r in rows if r["confident"] is not None]
    if known:
        out["confident"] = _rate(known, lambda r: bool(r["confident"]))
        # Confident and right: the top 3 has the answer and the search says so.
        out["confident_and_hit@3"] = _rate(
            known, lambda r: bool(r["confident"]) and (r["strict_rank"] or 99) <= 3
        )
    return out


def _distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    values = sorted(values)

    def pct(p: float) -> float:
        return round(values[min(len(values) - 1, int(p * len(values)))], 3)

    return {
        "min": round(values[0], 3),
        "p25": pct(0.25),
        "median": round(statistics.median(values), 3),
        "p75": pct(0.75),
        "max": round(values[-1], 3),
    }


def measure(questions: list[dict[str, Any]], k: int = K) -> dict[str, Any]:
    """Run every question and group the numbers: tuning vs holdout, it/en vs others."""
    rows = [run_question(q, k) for q in questions]
    report: dict[str, Any] = {"k": k, "rows": rows, "groups": {}, "unanswerable": {}}
    for split in ("tuning", "holdout"):
        part = [r for r in rows if r["holdout"] == (split == "holdout")]
        answerable = [r for r in part if r["answerable"]]
        if not answerable:
            continue
        groups = report["groups"]
        groups[f"{split}/it-en"] = summarise([r for r in answerable if r["lang"] in MAIN_LANGS])
        groups[f"{split}/other"] = summarise([r for r in answerable if r["lang"] not in MAIN_LANGS])
        groups[f"{split}/all"] = summarise(answerable)
        for lang in sorted({r["lang"] for r in answerable}):
            groups[f"{split}/lang:{lang}"] = summarise([r for r in answerable if r["lang"] == lang])
    unanswerable = [r for r in rows if not r["answerable"]]
    answerable_tuning = [r for r in rows if r["answerable"] and not r["holdout"]]
    report["unanswerable"] = {
        "n": len(unanswerable),
        "top_score": _distribution([r["top_score"] for r in unanswerable]),
        "answerable_top_score": _distribution([r["top_score"] for r in answerable_tuning]),
    }
    known = [r for r in unanswerable if r["confident"] is not None]
    if known:
        report["unanswerable"]["confident"] = _rate(known, lambda r: bool(r["confident"]))
        report["unanswerable"]["confidence"] = _distribution(
            [r["confidence"] for r in known if r["confidence"] is not None]
        )
        report["unanswerable"]["answerable_confidence"] = _distribution(
            [
                r["confidence"]
                for r in answerable_tuning
                if r["confident"] is not None and r["confidence"] is not None
            ]
        )
    return report


# ---------------------------------------------------------------- output


def _fmt(value: Any) -> str:
    return "" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))


def markdown(report: dict[str, Any]) -> str:
    """The report as Markdown: a table per group, the unanswerable scores, the failures."""
    cols = ["n", "hit@1", "hit@3", "hit@5", "page@1", "page@3", "page@5", "confident"]
    lines = [
        "# Retrieval on the ID card question bank",
        "",
        f"search(question, service_id={SERVICE!r}, k={report['k']}). A hit is an expected",
        "source whose passage contains or overlaps an evidence quote; page@k counts the",
        "source alone. 'confident' is the share of questions whose top result the search",
        "marks as a confident answer.",
        "",
        "| group | " + " | ".join(cols) + " |",
        "|---|" + "---:|" * len(cols),
    ]
    for name, g in report["groups"].items():
        lines.append(f"| {name} | " + " | ".join(_fmt(g.get(c)) for c in cols) + " |")
    u = report["unanswerable"]
    lines += [
        "",
        f"## Unanswerable and out of scope ({u['n']} questions)",
        "",
        "| | min | p25 | median | p75 | max |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, key in (
        ("top score, unanswerable", "top_score"),
        ("top score, answerable (tuning)", "answerable_top_score"),
        ("confidence, unanswerable", "confidence"),
        ("confidence, answerable (tuning)", "answerable_confidence"),
    ):
        d = u.get(key) or {}
        if d:
            lines.append(
                f"| {label} | "
                + " | ".join(_fmt(d.get(c)) for c in ("min", "p25", "median", "p75", "max"))
                + " |"
            )
    if "confident" in u:
        lines += ["", f"Unanswerable questions with a confident top result: {u['confident']:.3f}"]
        lines += [""]
        for r in report["rows"]:
            if not r["answerable"]:
                flag = "CONFIDENT" if r["confident"] else "low"
                lines.append(
                    f"- {r['id']} ({r['lang']}) {flag} {_fmt(r['confidence'])}: "
                    f"{r['question']} -> {', '.join(r['found'][:3]) or '(nothing)'}"
                )
    for split in ("tuning", "holdout"):
        failures = [
            r
            for r in report["rows"]
            if r["answerable"]
            and r["holdout"] == (split == "holdout")
            and (r["strict_rank"] or 99) > 3
        ]
        if not failures and split == "holdout":
            continue
        lines += ["", f"## Failures at k=3, {split} ({len(failures)})", ""]
        for r in failures:
            page = f"page@{r['page_rank']}" if r["page_rank"] else "no page"
            got = ", ".join(r["found"][:3]) or "(nothing)"
            lines.append(
                f"- {r['id']} ({r['lang']}, {r['facet']}, {page}): {r['question']}  \n"
                f"  expected {', '.join(r['expected'])}; got {got}"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--holdout", action="store_true", help="also run the holdout questions")
    ap.add_argument("--json", action="store_true", help="print the numbers as JSON")
    ap.add_argument("--out", type=pathlib.Path, default=None, help="write the Markdown report")
    ap.add_argument("-k", type=int, default=K)
    args = ap.parse_args(argv)
    bank = check_bank.load_bank()["questions"]
    questions = [q for q in bank if args.holdout or not q.get("holdout")]
    report = measure(questions, args.k)
    text = markdown(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    if args.json:
        slim = {key: value for key, value in report.items() if key != "rows"}
        sys.stdout.write(json.dumps(slim, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
