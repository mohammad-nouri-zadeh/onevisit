"""Check that every fact the agent can use is backed by its source.

    python data/tools/validate.py              # run before every push
    python data/tools/validate.py --links      # also check that source URLs answer

Rules for a requirement, step, step route, form-guide section or housing option marked "verified":
  - its source_id exists in data/sources.csv and has a saved snapshot;
  - it has a verified_at date;
  - its quote appears word for word in the snapshot (spacing, case and
    apostrophes are normalised). This is what stops a made-up requirement.
Exit code 1 if any rule fails, so a bad fact can't slip into the demo.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.request

DATA = pathlib.Path(__file__).resolve().parents[1]
STALE_DAYS = 90


def norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--links", action="store_true", help="request every source URL")
    args = ap.parse_args()

    errors, warnings = [], []
    with (DATA / "sources.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    sources = {}
    for r in rows:
        if r["id"] in sources:
            errors.append(f"sources.csv: duplicate id {r['id']}")
        sources[r["id"]] = r

    snapshots = {}
    for sid, s in sources.items():
        if s["snapshot"]:
            path = DATA / s["snapshot"]
            if path.exists():
                snapshots[sid] = norm(path.read_text(encoding="utf-8", errors="replace"))
            else:
                errors.append(f"sources.csv: {sid} snapshot {s['snapshot']} not found")
        elif s["status"] != "todo":
            warnings.append(f"sources.csv: {sid} has no snapshot saved")

    counts = {"verified": 0, "draft": 0, "todo": 0}
    today = dt.date.today()

    guide_counts = {"verified": 0}

    def check(where: str, item: dict, bucket: dict | None = None) -> None:
        status = item.get("status", "todo")
        bucket = counts if bucket is None else bucket
        bucket[status] = bucket.get(status, 0) + 1
        sid = item.get("source_id")
        if sid not in sources:
            errors.append(f"{where}: unknown source_id '{sid}'")
            return
        if status != "verified":
            return
        if not item.get("verified_at"):
            errors.append(f"{where}: verified but no verified_at date")
        elif (today - dt.date.fromisoformat(item["verified_at"])).days > STALE_DAYS:
            warnings.append(f"{where}: verified more than {STALE_DAYS} days ago, recheck")
        quote = item.get("quote", "")
        if not quote:
            errors.append(f"{where}: verified but no quote")
        elif sid not in snapshots:
            errors.append(f"{where}: source '{sid}' has no saved snapshot to check the quote against")
        elif norm(quote) not in snapshots[sid]:
            errors.append(f"{where}: quote not found in the saved source '{sid}': \"{quote[:80]}\"")

    for path in sorted((DATA / "services").glob("*.json")):
        try:
            svc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}: invalid JSON ({e})")
            continue
        for key in ("id", "title", "deciding_questions", "requirements"):
            if key not in svc:
                errors.append(f"{path.name}: missing '{key}'")
        questions = {q["id"]: q for q in svc.get("deciding_questions", [])}
        seen = set()
        for req in svc.get("requirements", []):
            where = f"{path.name} requirement '{req.get('id')}'"
            if req.get("id") in seen:
                errors.append(f"{where}: duplicate id")
            seen.add(req.get("id"))
            for q, allowed in (req.get("when") or {}).items():
                if q not in questions:
                    errors.append(f"{where}: 'when' uses unknown question '{q}'")
                elif "options" in questions[q] and not set(allowed) <= set(questions[q]["options"]):
                    errors.append(f"{where}: 'when' values {allowed} not in the options of '{q}'")
            check(where, req)
        for step in svc.get("steps", []):
            check(f"{path.name} step {step.get('order')}", step)
            for n, route in enumerate(step.get("routes") or [], start=1):
                check(f"{path.name} step {step.get('order')} route {n}", route)
        # The guide to the online form: section titles and housing options quote the City's pages.
        guide = svc.get("form_guide") or {}
        section_ids = set()
        for sec in guide.get("sections", []):
            section_ids.add(sec.get("id"))
            check(f"{path.name} form section '{sec.get('id')}'", sec, guide_counts)
        housing = questions.get("alloggio", {}).get("options", [])
        for opt in guide.get("housing_options", []):
            where = f"{path.name} housing option '{opt.get('answer')}'"
            if opt.get("answer") not in housing:
                errors.append(f"{where}: not an option of the question 'alloggio'")
            check(where, opt, guide_counts)
        for req in svc.get("requirements", []):
            if req.get("form_section") and req["form_section"] not in section_ids:
                errors.append(f"{path.name} requirement '{req.get('id')}': unknown form_section '{req['form_section']}'")

    # enti.json: every source exists; a verified role with a quote is checked like a requirement.
    enti_path = DATA / "enti.json"
    if enti_path.exists():
        for ente in json.loads(enti_path.read_text(encoding="utf-8")):
            where = f"enti.json '{ente.get('id')}'"
            for sid in ente.get("source_ids") or []:
                if sid not in sources:
                    errors.append(f"{where}: unknown source_id '{sid}'")
            if ente.get("quote"):
                sid = ente.get("quote_source_id") or (ente.get("source_ids") or [None])[0]
                if sid not in snapshots:
                    errors.append(f"{where}: source '{sid}' has no saved snapshot to check the quote against")
                elif norm(ente["quote"]) not in snapshots[sid]:
                    errors.append(f"{where}: quote not found in the saved source '{sid}': \"{ente['quote'][:80]}\"")

    offices = json.loads((DATA / "offices.json").read_text(encoding="utf-8"))
    flagged = [o for o in offices if o["data_issues"]]
    # An office detail confirmed by a saved page (e.g. the entrance of via Larga) quotes that page.
    for o in offices:
        conf = o.get("entrance_confirmed_by")
        if conf:
            sid = conf.get("source_id")
            if sid not in snapshots:
                errors.append(f"offices.json {o['id']}: entrance source '{sid}' has no saved snapshot")
            elif norm(conf.get("quote", "")) not in snapshots[sid]:
                errors.append(f"offices.json {o['id']}: entrance quote not found in '{sid}'")

    if args.links:
        for sid, s in sources.items():
            if not s["url"]:
                continue
            req = urllib.request.Request(s["url"], headers={"User-Agent": "Mozilla/5.0 OneVisit-validate"})
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    code = resp.status
            except urllib.error.HTTPError as e:
                code = e.code
            except Exception as e:  # network errors are reported, not fatal
                code = f"error: {e}"
            if code != 200:
                warnings.append(f"link {sid}: {s['url']} -> {code}")

    print(f"Requirements and steps: {counts.get('verified', 0)} verified, "
          f"{counts.get('draft', 0)} draft, {counts.get('todo', 0)} todo")
    print(f"Online form guide: {guide_counts.get('verified', 0)} section titles and housing options verified")
    print(f"Offices: {len(offices)} ({len(flagged)} with data issues in the City dataset)")
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print("OK" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
