"""Check the ID card question bank against the saved official pages.

    python data/eval/qa/check_bank.py             # report, exit 1 if any error
    python data/eval/qa/check_bank.py --json      # the same as JSON (counts, errors, warnings)
    python data/eval/qa/check_bank.py --bank other.yaml

Rules (an error fails the run):
  - ids are unique; lang, style and facet come from the lists below;
  - answerable questions: every expected source is a row of data/sources.csv with a
    saved page data/pages/<id>.md, every expected source has at least one evidence
    quote, every quote appears word for word in its page (spacing and typographic
    quotes normalised, case kept), and every quote's source is an expected source;
  - unanswerable questions: no expected sources and no evidence, a redirect URL,
    and, when redirect.source is given, that source exists and its page or its
    sources.csv URL contains the redirect URL; holdout only on answerable questions.
Warnings: very short quotes, holdout share outside 15-25%, facets with four or more
answerable questions and no holdout, a holdout question placed before the HOLDOUT banner.

Standard library only; PyYAML is used when installed, otherwise load_bank() reads the
JSON-valued YAML layout the bank is written in.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlsplit

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parents[1]
BANK = HERE / "cie-questions.yaml"

LANGS = {"it", "en", "es", "fr", "ar", "zh", "uk", "bn"}
STYLES = {"formal", "colloquial", "typo"}
FACETS = {
    "booking",
    "offices",
    "documents",
    "photo",
    "cost",
    "renewal",
    "validity",
    "loss_theft",
    "urgent",
    "minors",
    "foreigners",
    "non_residents",
    "home_service",
    "delivery",
    "pin_puk",
    "digital_identity",
    "organ_donation",
    "data_change",
    "travel",
    "at_the_desk",
    "card_info",
    "accessibility",
    "out_of_scope",
}
REQUIRED = (
    "id",
    "lang",
    "style",
    "facet",
    "answerable",
    "holdout",
    "question",
    "answer",
    "expected_sources",
)
MIN_QUOTE = 12  # characters, after normalisation: shorter is an error
SHORT_QUOTE = 20  # shorter than this is a warning


_QUOTES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"'})


def norm(text: str) -> str:
    """Collapse whitespace and typographic quotes, keep case (stricter than validate.py)."""
    text = text.translate(_QUOTES)
    return re.sub(r"\s+", " ", text).strip()


def load_bank(path: pathlib.Path = BANK) -> dict[str, Any]:
    """The bank as a dict ({"version", "questions"}); PyYAML when installed, else a reader
    for the layout the bank uses (one JSON value per line, evidence items as JSON objects)."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # optional: the bank also loads without it

        data: dict[str, Any] = yaml.safe_load(text)
        return data
    except ImportError:
        pass
    root: dict[str, Any] = {}
    item: dict[str, Any] | None = None
    open_list: list[Any] | None = None
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        try:
            if indent == 0 and body.startswith("- "):
                key, _, value = body[2:].partition(":")
                item = {key.strip(): json.loads(value)}
                root.setdefault("questions", []).append(item)
                open_list = None
            elif indent == 0:
                key, _, value = body.partition(":")
                root[key.strip()] = json.loads(value) if value.strip() else []
                item, open_list = None, None
            elif body.startswith("- ") and open_list is not None:
                open_list.append(json.loads(body[2:]))
            elif item is not None:
                key, _, value = body.partition(":")
                if value.strip():
                    item[key.strip()] = json.loads(value)
                    open_list = None
                else:
                    open_list = item[key.strip()] = []
            else:
                raise ValueError("line outside a question")
        except ValueError as exc:  # json.JSONDecodeError is a ValueError
            raise ValueError(f"{path.name}:{n}: cannot read {body[:60]!r} ({exc})") from None
    return root


def load_sources() -> dict[str, dict[str, str]]:
    with (DATA / "sources.csv").open(encoding="utf-8", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


_PAGES: dict[str, str | None] = {}


def page_text(source_id: str, sources: dict[str, dict[str, str]] | None = None) -> str | None:
    """Normalised body of data/pages/<id>.md (front matter dropped), or None if not saved."""
    if source_id not in _PAGES:
        path = DATA / "pages" / f"{source_id}.md"
        if not path.exists() and sources and sources.get(source_id, {}).get("snapshot"):
            path = DATA / sources[source_id]["snapshot"]
        if path.exists() and path.suffix == ".md":
            raw = path.read_text(encoding="utf-8", errors="replace")
            if raw.startswith("---"):
                end = raw.find("\n---", 3)
                raw = raw[end + 4 :] if end != -1 else raw
            _PAGES[source_id] = norm(raw)
        else:
            _PAGES[source_id] = None
    return _PAGES[source_id]


def quote_found(source_id: str, quote: str) -> bool:
    """True when the quote appears word for word in the saved page of source_id."""
    text = page_text(source_id)
    return text is not None and norm(quote) in text


def _linked_from(url: str, source_id: str, sources: dict[str, dict[str, str]]) -> bool:
    """True when url is the source's own URL, or the saved page links to it (absolute,
    or relative on the same host)."""
    own = sources[source_id]["url"]
    if own.rstrip("/") == url.rstrip("/"):
        return True
    text = page_text(source_id, sources) or ""
    if url in text:
        return True
    target, home = urlsplit(url), urlsplit(own)
    return target.netloc == home.netloc and len(target.path) > 1 and f"]({target.path}" in text


def check(bank: dict[str, Any]) -> tuple[list[str], list[str], dict[str, Any]]:
    sources = load_sources()
    errors: list[str] = []
    warnings: list[str] = []
    qs = bank.get("questions") or []
    seen_ids: set[str] = set()
    seen_q: dict[str, str] = {}
    first_holdout = None
    for pos, q in enumerate(qs):
        qid = str(q.get("id", f"#{pos}"))
        missing = [k for k in REQUIRED if k not in q]
        if missing:
            errors.append(f"{qid}: missing {', '.join(missing)}")
            continue
        if qid in seen_ids:
            errors.append(f"{qid}: duplicate id")
        seen_ids.add(qid)
        if not re.fullmatch(r"cie-[a-z-]+-\d{2}", qid):
            errors.append(f"{qid}: id must look like cie-<facet>-<nn>")
        if q["lang"] not in LANGS:
            errors.append(f"{qid}: unknown lang {q['lang']!r}")
        if q["style"] not in STYLES:
            errors.append(f"{qid}: unknown style {q['style']!r}")
        if q["facet"] not in FACETS:
            errors.append(f"{qid}: unknown facet {q['facet']!r}")
        if not isinstance(q["answerable"], bool) or not isinstance(q["holdout"], bool):
            errors.append(f"{qid}: answerable and holdout must be true/false")
        key = norm(str(q["question"])).casefold()
        if key in seen_q:
            errors.append(f"{qid}: same question as {seen_q[key]}")
        seen_q[key] = qid
        if not str(q["question"]).strip() or not str(q["answer"]).strip():
            errors.append(f"{qid}: empty question or answer")
        if q["holdout"] and first_holdout is None:
            first_holdout = pos
        if not q["holdout"] and first_holdout is not None:
            warnings.append(f"{qid}: not holdout but placed after the first holdout question")

        exp = q["expected_sources"] or []
        evidence = q.get("evidence") or []
        if q["answerable"]:
            if q["facet"] == "out_of_scope":
                errors.append(f"{qid}: out_of_scope questions must be answerable: false")
            if not exp:
                errors.append(f"{qid}: answerable but no expected_sources")
            if not evidence:
                errors.append(f"{qid}: answerable but no evidence")
            for sid in exp:
                if sid not in sources:
                    errors.append(f"{qid}: expected source {sid} not in data/sources.csv")
                elif page_text(sid, sources) is None:
                    errors.append(
                        f"{qid}: expected source {sid} has no saved page data/pages/{sid}.md"
                    )
            quoted = set()
            for ev in evidence:
                sid, quote = ev.get("source"), ev.get("quote") or ""
                quoted.add(sid)
                if sid not in exp:
                    errors.append(f"{qid}: evidence source {sid} is not in expected_sources")
                if len(norm(quote)) < MIN_QUOTE:
                    errors.append(f"{qid}: quote from {sid} too short: {quote!r}")
                elif len(norm(quote)) < SHORT_QUOTE:
                    warnings.append(f"{qid}: short quote from {sid}: {quote!r}")
                text = page_text(sid, sources) if sid in sources else None
                if text is not None and norm(quote) not in text:
                    errors.append(f"{qid}: quote not found in data/pages/{sid}.md: {quote[:90]!r}")
            for sid in exp:
                if sid not in quoted:
                    errors.append(f"{qid}: expected source {sid} has no evidence quote")
        else:
            if exp or evidence:
                errors.append(f"{qid}: unanswerable questions take no expected_sources or evidence")
            if q["holdout"]:
                errors.append(f"{qid}: holdout is only for answerable questions")
            red = q.get("redirect") or {}
            url = red.get("url", "")
            if not re.match(r"https?://", url):
                errors.append(f"{qid}: unanswerable question needs redirect.url")
            rsid = red.get("source")
            if rsid:
                if rsid not in sources:
                    errors.append(f"{qid}: redirect source {rsid} not in data/sources.csv")
                elif not _linked_from(url, rsid, sources):
                    errors.append(
                        f"{qid}: redirect url is neither the URL of {rsid} nor linked from its page"
                    )
            for sid in q.get("related_sources") or []:
                if sid not in sources:
                    errors.append(f"{qid}: related source {sid} not in data/sources.csv")
            if not str(q.get("why", "")).strip():
                errors.append(f"{qid}: unanswerable question needs why")

    answerable = [q for q in qs if q.get("answerable") is True]
    holdout = [q for q in answerable if q.get("holdout")]
    by_facet: dict[str, Counter[str]] = defaultdict(Counter)
    for q in qs:
        c = by_facet[q.get("facet", "?")]
        c["total"] += 1
        c["answerable" if q.get("answerable") else "unanswerable"] += 1
        c["holdout"] += bool(q.get("holdout"))
    share = len(holdout) / len(answerable) if answerable else 0.0
    if not 0.15 <= share <= 0.25:
        warnings.append(f"holdout share {share:.0%} of answerable questions, expected about 20%")
    for facet, c in sorted(by_facet.items()):
        if c["answerable"] >= 4 and not c["holdout"]:
            warnings.append(
                f"facet {facet}: {c['answerable']} answerable questions, none in holdout"
            )
    stats = {
        "questions": len(qs),
        "answerable": len(answerable),
        "unanswerable": sum(
            1 for q in qs if q.get("answerable") is False and q.get("facet") != "out_of_scope"
        ),
        "out_of_scope": sum(1 for q in qs if q.get("facet") == "out_of_scope"),
        "holdout": len(holdout),
        "holdout_share": round(share, 3),
        "evidence_quotes": sum(len(q.get("evidence") or []) for q in qs),
        "sources_used": len({s for q in qs for s in (q.get("expected_sources") or [])}),
        "by_lang": dict(Counter(q.get("lang") for q in qs).most_common()),
        "by_style": dict(Counter(q.get("style") for q in qs).most_common()),
        "by_facet": {f: dict(c) for f, c in sorted(by_facet.items())},
    }
    return errors, warnings, stats


def _out(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bank", type=pathlib.Path, default=BANK)
    ap.add_argument("--json", action="store_true", help="print counts, errors and warnings as JSON")
    args = ap.parse_args()
    try:
        bank = load_bank(args.bank)
    except (OSError, ValueError) as exc:
        _out(f"ERROR {exc}")
        return 1
    errors, warnings, stats = check(bank)
    if args.json:
        _out(
            json.dumps(
                {"stats": stats, "errors": errors, "warnings": warnings},
                ensure_ascii=False,
                indent=1,
            )
        )
        return 1 if errors else 0
    s = stats
    _out(
        f"{args.bank.name}: {s['questions']} questions: {s['answerable']} answerable "
        f"({s['holdout']} holdout, {s['holdout_share']:.0%}), {s['unanswerable']} unanswerable, "
        f"{s['out_of_scope']} out of scope; "
        f"{s['evidence_quotes']} evidence quotes from {s['sources_used']} pages"
    )
    _out("languages: " + ", ".join(f"{k} {v}" for k, v in s["by_lang"].items()))
    _out("styles:    " + ", ".join(f"{k} {v}" for k, v in s["by_style"].items()))
    _out(f"\n{'facet':<18}{'total':>6}{'answ.':>7}{'unansw.':>9}{'holdout':>9}")
    for facet, c in s["by_facet"].items():
        _out(
            f"{facet:<18}{c.get('total', 0):>6}{c.get('answerable', 0):>7}"
            f"{c.get('unanswerable', 0):>9}{c.get('holdout', 0):>9}"
        )
    for w in warnings:
        _out(f"WARNING {w}")
    for e in errors:
        _out(f"ERROR {e}")
    _out(f"\n{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
