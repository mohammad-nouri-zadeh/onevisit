"""Check that every fact the agent can use is backed by its source.

    python data/tools/validate.py              # run before every push
    python data/tools/validate.py --links      # also check that source URLs answer

Rules for a requirement or step marked "verified":
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

    def check(where: str, item: dict) -> None:
        status = item.get("status", "todo")
        counts[status] = counts.get(status, 0) + 1
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

    offices = json.loads((DATA / "offices.json").read_text(encoding="utf-8"))
    flagged = [o for o in offices if o["data_issues"]]

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
    print(f"Offices: {len(offices)} ({len(flagged)} with data issues in the City dataset)")
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print("OK" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
