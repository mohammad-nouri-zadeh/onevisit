"""OneVisit knowledge base: the only way the agent reads City facts.

The agent never answers a factual question from model memory. It calls these
functions (through the tools in onevisit/tools.py) and cites `source_id`s.

Only facts with status "verified" are returned, unless ONEVISIT_INCLUDE_DRAFTS=1
is set for development. A verified fact has a verbatim quote that
data/tools/validate.py has found inside the saved copy of its source.

    python -m onevisit.kb                      # quick self-check
"""
from __future__ import annotations

import csv
import json
import math
import os
import pathlib

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"


def _include_drafts() -> bool:
    return os.getenv("ONEVISIT_INCLUDE_DRAFTS") == "1"


def _usable(item: dict) -> bool:
    return item.get("status") == "verified" or _include_drafts()


def sources() -> dict[str, dict]:
    with (DATA / "sources.csv").open(encoding="utf-8", newline="") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def get_source(source_id: str) -> dict | None:
    """Title, URL, publisher and retrieval date of one source."""
    s = sources().get(source_id)
    if not s:
        return None
    return {k: s[k] for k in ("id", "title", "url", "publisher", "retrieved_at", "status")}


def _services() -> dict[str, dict]:
    out = {}
    for path in sorted((DATA / "services").glob("*.json")):
        svc = json.loads(path.read_text(encoding="utf-8"))
        out[svc["id"]] = svc
    return out


def list_services() -> list[dict]:
    """The services OneVisit covers, with how many requirements are verified."""
    result = []
    for svc in _services().values():
        reqs = svc.get("requirements", [])
        result.append({
            "id": svc["id"],
            "title": svc["title"],
            "verified_requirements": sum(r.get("status") == "verified" for r in reqs),
            "total_requirements": len(reqs),
        })
    return result


def get_service(service_id: str) -> dict | None:
    """Questions that change the answer, plus the steps across offices, for one service."""
    svc = _services().get(service_id)
    if not svc:
        return None
    return {
        "id": svc["id"],
        "title": svc["title"],
        "ente": svc.get("ente"),
        "deciding_questions": svc.get("deciding_questions", []),
        "steps": [s for s in svc.get("steps", []) if _usable(s)],
        "unknowns_it": svc.get("unknowns_it", []),
    }


def checklist(service_id: str, answers: dict | None = None) -> dict:
    """Requirements that apply to this case, each with its source.

    `answers` maps deciding-question ids to the citizen's answer, e.g.
    {"motivo": "smarrimento-furto", "eta": "adulto"}. A requirement whose
    condition depends on an unanswered question is left out and that question
    is listed in `still_to_ask`.
    """
    svc = _services().get(service_id)
    if not svc:
        return {"error": f"Unknown service '{service_id}'. Call list_services first."}
    answers = answers or {}
    applies, still_to_ask, not_verified = [], set(), []
    for req in svc.get("requirements", []):
        when = req.get("when") or {}
        missing = [q for q in when if q not in answers]
        if missing:
            still_to_ask.update(missing)
            continue
        if not all(answers[q] in allowed for q, allowed in when.items()):
            continue
        if not _usable(req):
            not_verified.append(req["id"])
            continue
        applies.append({
            "id": req["id"],
            "text_it": req["text_it"],
            "text_en": req.get("text_en"),
            "source_id": req["source_id"],
            "quote": req.get("quote"),
            "verified_at": req.get("verified_at"),
            "status": req.get("status"),
        })
    cited = sorted({r["source_id"] for r in applies})
    return {
        "service_id": service_id,
        "requirements": applies,
        "still_to_ask": sorted(still_to_ask),
        "not_yet_verified": not_verified,
        "sources": [get_source(s) for s in cited],
        "note": "Requirements in not_yet_verified exist but are not checked against a source: "
                "say you don't know them and point to the official page.",
    }


def _offices() -> list[dict]:
    return json.loads((DATA / "offices.json").read_text(encoding="utf-8"))


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def find_offices(area: str | None = None, municipio: int | None = None,
                 lat: float | None = None, lon: float | None = None, limit: int = 3) -> list[dict]:
    """Registry offices (open dataset ds549) by neighbourhood name, Municipio, or distance."""
    offices = _offices()
    if municipio is not None:
        offices = [o for o in offices if o["municipio"] == municipio]
    if area:
        needle = area.lower()
        offices = [o for o in offices if needle in o["nil"]["name"].lower() or needle in o["address"].lower()]
    if lat is not None and lon is not None:
        for o in offices:
            o["distance_km"] = round(_km(lat, lon, o["lat"], o["lon"]), 2)
        offices.sort(key=lambda o: o["distance_km"])
    keep = ("id", "municipio", "address", "entrance_note", "phone", "hours_it", "notes_it",
            "booking_without_spid", "nil", "distance_km", "source_id", "data_issues")
    return [{k: o[k] for k in keep if k in o} for o in offices[:limit]]


def prompt_context() -> str:
    """A compact index of what the knowledge base covers, for the system prompt."""
    lines = ["Services covered (call get_service / get_checklist for details):"]
    for s in list_services():
        lines.append(f"- {s['id']}: {s['title']['it']} "
                     f"({s['verified_requirements']}/{s['total_requirements']} requirements verified)")
    lines.append(f"Registry offices: {len(_offices())} (call find_offices).")
    return "\n".join(lines)


if __name__ == "__main__":
    print(prompt_context())
    print(json.dumps(checklist("carta-identita", {"motivo": "rinnovo"}), ensure_ascii=False, indent=2)[:1500])
    print(json.dumps(find_offices(lat=45.4847, lon=9.2025), ensure_ascii=False, indent=2)[:800])
