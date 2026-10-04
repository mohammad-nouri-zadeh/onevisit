"""After the appointment: Claude classifies what went wrong and drafts page fixes.

Reports are stored without personal data. A group of similar reports reaches the
office only above THRESHOLD; below it, only the web editors see it (concept doc,
"Il ciclo di miglioramento"). Nothing is published without a person approving it.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import re

import anthropic

from onevisit.agent import FALLBACK, MODEL

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATED = ROOT / "data" / "demo" / "simulated-outcomes.json"
RUNTIME = ROOT / "runtime" / "outcomes.jsonl"
EXAMPLES = ROOT / "data" / "demo" / "classifications.json"
THRESHOLD = 5

CAUSES = {
    "pagina-incompleta": ("Page incomplete", "Web editors (redazione web)"),
    "procedura-non-aggiornata": ("Procedure out of date", "Office that owns the procedure"),
    "procedura-mancante": ("No page for this case", "Office that owns the procedure, and web editors"),
    "ufficio-sbagliato": ("Wrong body or office indicated", "Web editors (redazione web)"),
    "non-seguita": ("Page was clear, not followed", "Nobody: improve the assistant"),
    "richiesta-non-prevista": ("Desk asked for something the procedure doesn't require", "Head of service, per procedure and per office"),
}

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "cause": {"type": "string", "enum": list(CAUSES)},
        "summary_it": {"type": "string", "description": "One general sentence in Italian, no personal data"},
        "summary_en": {"type": "string", "description": "The same sentence in English"},
    },
    "required": ["cause", "summary_it", "summary_en"],
    "additionalProperties": False,
}


# Personal details removed from a report before it reaches Claude (and before anything is stored).
_PII = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("codice_fiscale", re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.IGNORECASE)),
    ("iban", re.compile(r"\bIT\d{2}[A-Z]\d{10}[0-9A-Z]{12}\b", re.IGNORECASE)),
    ("data", re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b")),
    ("telefono", re.compile(r"(?<!\w)\+?\d[\d\s./-]{7,}\d")),
    ("numero_documento", re.compile(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{7,12}\b")),
)


def scrub(note: str) -> tuple[str, list[str]]:
    """Replace emails, tax codes, IBANs, dates, phone and document numbers with a placeholder.

    Returns the cleaned text and the kinds removed (never the values), so the citizen can
    see what was taken out before Claude reads the report.
    """
    removed: list[str] = []
    text = note or ""
    for kind, pattern in _PII:
        text, n = pattern.subn(f"[{kind}]", text)
        removed += [kind] * n
    return text, removed


def _text(resp) -> str:
    return "".join(b.text for b in resp.content if b.type == "text")


def classify(service_id: str, outcome: str, note: str, client: anthropic.Anthropic | None = None) -> dict:
    """Turn one citizen's free-text report into a cause and a general, anonymous summary.

    The note is scrubbed of emails, tax codes and document or phone numbers first (`scrub`),
    so those never reach the model; Claude removes the remaining personal details.
    """
    client = client or anthropic.Anthropic()
    note, _ = scrub(note)
    prompt = (
        f"A citizen used OneVisit to prepare for the service '{service_id}' at the City of Milan registry office. "
        f"After the appointment they reported: outcome='{outcome}', note='{note}'.\n"
        "Classify the most likely cause, using these meanings:\n"
        + "\n".join(f"- {k}: {v[0]}" for k, v in CAUSES.items())
        + "\nThen write one general sentence describing the problem, with every personal detail removed "
          "(no names, dates, nationalities, document numbers, places tied to the person)."
    )
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=4000, messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA}}, **FALLBACK,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("The model declined to classify this report.")
    return json.loads(_text(resp))


def recorded_classification(note: str) -> dict | None:
    """Demo without a key: Claude's recorded classification of one of the example reports."""
    data = json.loads(EXAMPLES.read_text(encoding="utf-8")) if EXAMPLES.exists() else {}
    for ex in data.get("examples", []):
        if note.strip() in ex["note"].values():
            return ex["result"]
    return None


def example_notes(lang: str) -> list[str]:
    """The example reports offered in the demo, in the interface language (Italian or English)."""
    data = json.loads(EXAMPLES.read_text(encoding="utf-8")) if EXAMPLES.exists() else {}
    return [ex["note"].get(lang) or ex["note"]["en"] for ex in data.get("examples", [])]


def save_report(service_id: str, outcome: str, result: dict) -> dict:
    """Store only the structured fields; the citizen's own words are discarded."""
    RUNTIME.parent.mkdir(exist_ok=True)
    week = dt.date.today().isocalendar()
    row = {"service_id": service_id, "outcome": outcome, "cause": result["cause"],
           "summary_it": result["summary_it"], "summary_en": result["summary_en"],
           "week": f"{week.year}-W{week.week:02d}", "simulated": False}
    with RUNTIME.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def all_reports() -> list[dict]:
    rows = json.loads(SIMULATED.read_text(encoding="utf-8")) if SIMULATED.exists() else []
    if RUNTIME.exists():
        rows += [json.loads(line) for line in RUNTIME.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


def groups() -> list[dict]:
    """Reports grouped by service and cause, largest first."""
    by_key = collections.defaultdict(list)
    for r in all_reports():
        if r["outcome"] != "ok":
            by_key[(r["service_id"], r["cause"])].append(r)
    out = []
    for (service_id, cause), rows in by_key.items():
        label, recipient = CAUSES[cause]
        out.append({
            "service_id": service_id, "cause": cause, "cause_label": label, "recipient": recipient,
            "count": len(rows), "simulated": sum(r.get("simulated", False) for r in rows),
            "over_threshold": len(rows) >= THRESHOLD,
            "examples_en": sorted({r["summary_en"] for r in rows})[:5],
            "examples_it": sorted({r["summary_it"] for r in rows})[:5],
        })
    return sorted(out, key=lambda g: -g["count"])


def draft_fix(group: dict, client: anthropic.Anthropic | None = None) -> str:
    """Claude drafts the correction for the page; a person must approve it."""
    client = client or anthropic.Anthropic()
    prompt = (
        "You help the City of Milan's web editors fix service pages. "
        f"For the service '{group['service_id']}', {group['count']} citizens reported the same kind of problem "
        f"({group['cause_label']}). Their anonymised reports:\n- " + "\n- ".join(group["examples_it"]) +
        "\n\nWrite, in Italian: (1) one sentence on what the page is probably missing or getting wrong; "
        "(2) the exact text to add or change on the page, as a short draft; (3) one line on what the office "
        "must confirm before publishing, because you can't verify the rule yourself. Under 120 words. "
        "Start with 'BOZZA DA APPROVARE'."
    )
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=4000, messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low"}, **FALLBACK,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("The model declined to draft this correction.")
    return _text(resp).strip()
