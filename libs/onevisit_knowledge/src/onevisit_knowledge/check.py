"""Validazione del catalogo: ogni fatto verificato ha la sua fonte e la sua citazione (storia A2).

Stesse regole di ``data/tools/validate.py``, più:

- ogni ``source_id`` di requisiti e passaggi esiste in ``sources.csv`` (anche se ``todo``);
- un fatto verificato ha una citazione non vuota trovata alla lettera (spazi, maiuscole e
  apostrofi normalizzati) in ``data/pages/<source_id>.md`` (senza front matter) oppure nello
  snapshot indicato in ``sources.csv``, e una data ``verified_at`` valida;
- le domande citate nei ``when`` esistono e le opzioni usate sono tra le sue;
- gli enti dei servizi e dei passaggi esistono in ``enti.json``, le fonti degli enti in
  ``sources.csv``.

I requisiti ``todo`` sono ammessi: non vengono mai mostrati al cittadino.
"""

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from onevisit_knowledge.text import normalize, split_front_matter

VERIFIED = "verified"
# Oltre questi giorni una verifica produce un avviso (come STALE_DAYS di validate.py).
STALE_DAYS = 90


@dataclass
class CatalogReport:
    """Esito completo della validazione: errori, avvisi e conteggi per il riepilogo."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    offices: int = 0
    offices_with_issues: int = 0


def _load_texts(
    data_dir: Path, sources: dict[str, dict[str, str]], report: CatalogReport
) -> dict[str, list[str]]:
    """Testi normalizzati in cui cercare le citazioni di ciascuna fonte."""
    texts: dict[str, list[str]] = {}
    for sid, row in sources.items():
        candidates: list[Path] = []
        page = data_dir / "pages" / f"{sid}.md"
        if page.exists():
            candidates.append(page)
        snapshot = row.get("snapshot") or ""
        if snapshot:
            snap_path = data_dir / snapshot
            if snap_path.exists():
                if snap_path != page:
                    candidates.append(snap_path)
            else:
                report.errors.append(f"sources.csv: {sid} snapshot {snapshot} not found")
        elif row.get("status") != "todo" and not page.exists():
            report.warnings.append(f"sources.csv: {sid} has no snapshot saved")
        for path in candidates:
            _, body = split_front_matter(path.read_text(encoding="utf-8", errors="replace"))
            texts.setdefault(sid, []).append(normalize(body))
    return texts


def inspect_catalog(data_dir: Path, *, today: date | None = None) -> CatalogReport:
    """Valida il catalogo e restituisce errori, avvisi e conteggi."""
    data_dir = Path(data_dir)
    today = today or date.today()
    report = CatalogReport(counts={"verified": 0, "draft": 0, "todo": 0})

    try:
        with (data_dir / "sources.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except FileNotFoundError:
        report.errors.append("sources.csv: file not found")
        rows = []
    sources: dict[str, dict[str, str]] = {}
    for row in rows:
        if row["id"] in sources:
            report.errors.append(f"sources.csv: duplicate id {row['id']}")
        sources[row["id"]] = row
    texts = _load_texts(data_dir, sources, report)

    enti_ids: set[str] | None = None
    enti_path = data_dir / "enti.json"
    if enti_path.exists():
        try:
            enti = json.loads(enti_path.read_text(encoding="utf-8"))
            enti_ids = {e["id"] for e in enti}
            for ente in enti:
                for sid in ente.get("source_ids") or []:
                    if sid not in sources:
                        report.errors.append(f"enti.json '{ente['id']}': unknown source_id '{sid}'")
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            report.errors.append(f"enti.json: invalid ({exc})")

    def check_ente(where: str, ente: Any) -> None:
        if ente and enti_ids is not None and ente not in enti_ids:
            report.errors.append(f"{where}: unknown ente '{ente}'")

    def check(where: str, item: dict[str, Any]) -> None:
        status = item.get("status", "todo")
        report.counts[status] = report.counts.get(status, 0) + 1
        sid = item.get("source_id")
        if sid not in sources:
            report.errors.append(f"{where}: unknown source_id '{sid}'")
            return
        if status != VERIFIED:
            return
        verified_at = item.get("verified_at")
        if not verified_at:
            report.errors.append(f"{where}: verified but no verified_at date")
        else:
            try:
                age = (today - date.fromisoformat(str(verified_at))).days
            except ValueError:
                report.errors.append(f"{where}: verified_at '{verified_at}' is not a date")
            else:
                if age > STALE_DAYS:
                    report.warnings.append(
                        f"{where}: verified more than {STALE_DAYS} days ago, recheck"
                    )
        quote = item.get("quote") or ""
        if not quote.strip():
            report.errors.append(f"{where}: verified but no quote")
        elif sid not in texts:
            report.errors.append(
                f"{where}: source '{sid}' has no saved page to check the quote against"
            )
        elif not any(normalize(quote) in text for text in texts[sid]):
            report.errors.append(
                f"{where}: quote not found in the saved source '{sid}': \"{quote[:80]}\""
            )

    for path in sorted((data_dir / "services").glob("*.json")):
        try:
            svc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.errors.append(f"{path.name}: invalid JSON ({exc})")
            continue
        for key in ("id", "title", "deciding_questions", "requirements"):
            if key not in svc:
                report.errors.append(f"{path.name}: missing '{key}'")
        check_ente(path.name, svc.get("ente"))
        for sid in svc.get("source_ids") or []:
            if sid not in sources:
                report.errors.append(f"{path.name}: unknown source_id '{sid}' in source_ids")
        questions = {q["id"]: q for q in svc.get("deciding_questions", [])}
        seen: set[str] = set()
        for req in svc.get("requirements", []):
            where = f"{path.name} requirement '{req.get('id')}'"
            if req.get("id") in seen:
                report.errors.append(f"{where}: duplicate id")
            seen.add(req.get("id"))
            for qid, allowed in (req.get("when") or {}).items():
                if qid not in questions:
                    report.errors.append(f"{where}: 'when' uses unknown question '{qid}'")
                elif "options" in questions[qid] and not set(allowed) <= set(
                    questions[qid]["options"]
                ):
                    report.errors.append(
                        f"{where}: 'when' values {allowed} not in the options of '{qid}'"
                    )
            check(where, req)
        for step in svc.get("steps", []):
            where = f"{path.name} step {step.get('order')}"
            check_ente(where, step.get("ente"))
            check(where, step)

    try:
        offices = json.loads((data_dir / "offices.json").read_text(encoding="utf-8"))
        report.offices = len(offices)
        report.offices_with_issues = sum(1 for o in offices if o.get("data_issues"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        report.errors.append(f"offices.json: cannot be read ({exc.__class__.__name__})")
    return report


def check_catalog(data_dir: Path) -> list[str]:
    """Errori leggibili; lista vuota = catalogo valido."""
    return inspect_catalog(data_dir).errors
