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
import functools
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
    """Questions that change the answer, the steps across offices and the official links of one service."""
    svc = _services().get(service_id)
    if not svc:
        return None
    return {
        "id": svc["id"],
        "title": svc["title"],
        "ente": svc.get("ente"),
        "summary_it": svc.get("summary_it"),
        "summary_en": svc.get("summary_en"),
        "links": service_links(service_id),
        "deciding_questions": svc.get("deciding_questions", []),
        "steps": [_step(s) for s in svc.get("steps", []) if _usable(s)],
        "has_form_guide": bool(svc.get("form_guide")),
        "online_form_kind": svc.get("online_form_kind") or ("city" if svc.get("online_form_url") else None),
        "unknowns_it": svc.get("unknowns_it", []),
    }


def _step(step: dict) -> dict:
    """A step with only its verified alternative routes (e.g. who assigns the tax code)."""
    out = {k: v for k, v in step.items() if k != "routes"}
    routes = [r for r in step.get("routes") or [] if _usable(r)]
    if routes:
        out["routes"] = routes
    return out


LINK_KINDS = ("official_url", "booking_url", "online_form_url")


def _page_text(source: dict) -> str:
    snapshot = (source.get("snapshot") or "").strip()
    path = DATA / snapshot if snapshot else None
    if not path or path.suffix != ".md" or not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=64)
def link_source(url: str, prefer: tuple[str, ...] = ()) -> str | None:
    """The source that backs a link: the saved source at that URL, else the first saved page
    that contains the link (the service's own sources, `prefer`, first). None if no saved
    source has it (then the link is not shown)."""
    if not url:
        return None
    catalogue = sources()
    for sid, row in catalogue.items():
        if row.get("url") == url:
            return sid
    ordered = [s for s in prefer if s in catalogue] + [s for s in catalogue if s not in prefer]
    for sid in ordered:
        if url in _page_text(catalogue[sid]):
            return sid
    return None


def service_links(service_id: str) -> dict[str, dict]:
    """Official page, booking page and online form of a service, each with the source that has it.

    {"booking_url": {"url": "https://...", "source_id": "cie"}, ...}; a link with no saved
    source behind it is left out.
    """
    svc = _services().get(service_id) or {}
    out = {}
    for kind in LINK_KINDS:
        url = svc.get(kind)
        sid = link_source(url, tuple(svc.get("source_ids") or ())) if url else None
        if url and sid:
            out[kind] = {"url": url, "source_id": sid}
    return out


def open_items(service_id: str, ids: list[str]) -> list[dict]:
    """The requirements in a checklist's not_yet_verified, with the official page to check them on.

    Their text says what is still unknown ("Da verificare: ..."); it is not a City rule.
    """
    svc = _services().get(service_id) or {}
    by_id = {r["id"]: r for r in svc.get("requirements", [])}
    catalogue = sources()
    out = []
    for rid in ids:
        req = by_id.get(rid)
        if not req:
            continue
        sid = req.get("source_id") or ""
        out.append({
            "id": rid,
            "text_it": req.get("text_it"),
            "text_en": req.get("text_en"),
            "source_id": sid,
            "url": svc.get("official_url") or (catalogue.get(sid) or {}).get("url") or "https://www.comune.milano.it",
        })
    return out


# Order in which the app and the dossier show a checklist's categories.
CATEGORIES = ("prepare", "how", "if-urgent", "after")


def checklist(service_id: str, answers: dict | None = None) -> dict:
    """Requirements that apply to this case, each with its source.

    `answers` maps deciding-question ids to the citizen's answer, e.g.
    {"motivo": "smarrimento-furto", "eta": "adulto"}. A requirement whose
    condition depends on an unanswered question is left out and that question
    is listed in `still_to_ask`. Each requirement has a `category`: what to
    prepare, how the procedure works, what happens after, what to do if urgent.
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
        item = {
            "id": req["id"],
            "text_it": req["text_it"],
            "text_en": req.get("text_en"),
            "category": req.get("category") or "prepare",
            "source_id": req["source_id"],
            "quote": req.get("quote"),
            "verified_at": req.get("verified_at"),
            "status": req.get("status"),
        }
        for key in ("short_it", "short_en", "form_section", "urgent_lead", "lead_time_days"):
            if req.get(key) is not None:
                item[key] = req[key]
        applies.append(item)
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


# Sections of a checklist item that are files to upload (or things to bring), in the order
# of the City's Modulistica page; "nel-modulo" and "invio" are instructions, not files.
UPLOAD_SECTIONS = ("dichiarazione", "base", "cittadinanza", "abitazione", "minori")


def form_guide(service_id: str, answers: dict | None = None) -> dict:
    """How to fill in the City's online application for this case, from the verified data.

    The sections follow the City's Modulistica page (each title quotes it); every applicable
    checklist item sits in its section; the housing option is the page's own wording for the
    citizen's answer. Nothing here names a field of the online form that no saved source shows.
    """
    svc = _services().get(service_id)
    if not svc:
        return {"error": f"Unknown service '{service_id}'. Call list_services first."}
    guide = svc.get("form_guide")
    if not guide:
        return {"service_id": service_id, "sections": [], "note": "This service has no online form: it is done at a desk."}
    answers = answers or {}
    cl = checklist(service_id, answers)
    by_section: dict[str, list[dict]] = {}
    for r in cl["requirements"]:
        if r.get("form_section"):
            by_section.setdefault(r["form_section"], []).append(
                {k: r.get(k) for k in ("id", "text_it", "text_en", "short_it", "short_en", "source_id")})
    sections = []
    for sec in guide.get("sections", []):
        if not _usable(sec):
            continue
        items = by_section.get(sec["id"], [])
        if not items and sec["id"] not in ("dichiarazione", "invio"):
            continue
        sections.append({**{k: sec.get(k) for k in ("id", "title_it", "title_en", "text_it", "text_en",
                                                    "source_id", "quote", "verified_at")}, "items": items})
    housing = next((h for h in guide.get("housing_options", [])
                    if h.get("answer") == answers.get("alloggio") and _usable(h)), None)
    links = service_links(service_id)
    return {
        "service_id": service_id,
        "form": links.get(guide.get("form_url_kind", "online_form_url")),
        "sections": sections,
        "housing_option": ({k: housing.get(k) for k in ("answer", "label_it", "label_en", "source_id", "quote")}
                           if housing else None),
        "still_to_ask": cl["still_to_ask"],
        "note": "Section titles and the housing option quote the City's Modulistica page. The saved sources don't show "
                "the online form's own fields: don't name buttons or fields that are not here.",
    }


def to_upload(checklist_result: dict) -> list[dict]:
    """The files to upload (online) or things to bring (desk): checklist items with a short name,
    in the order of the City's Modulistica sections, then the rest of 'prepare'."""
    reqs = [r for r in checklist_result.get("requirements", []) if r.get("short_it")]
    order = {sec: n for n, sec in enumerate(UPLOAD_SECTIONS)}
    files = [r for r in reqs if r.get("form_section") in order]
    if files:
        return sorted(files, key=lambda r: order[r["form_section"]])
    return [r for r in reqs if (r.get("category") or "prepare") == "prepare"]


# ---------- the citizen's language ----------
# Requirement, step and section texts exist in Italian and English in data/services. For
# Arabic, Spanish and Chinese, data/i18n/requirements.<lang>.json holds Claude's translation
# of each text, keyed by service and item, with the Italian it was made from: a translation
# whose Italian has changed since is stale and not used. The Italian text and the verbatim
# quote stay authoritative; the app labels these texts as Claude's translation.
I18N = DATA / "i18n"
_RUNTIME_TRANSLATIONS: dict[str, dict[str, dict]] = {}


@functools.lru_cache(maxsize=8)
def _translation_file(lang: str) -> dict:
    path = I18N / f"requirements.{lang}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("texts", {})


def text_key(service_id: str, kind: str, item_id: object, field: str = "text") -> str:
    """'carta-identita:req:costo:text', 'iscrizione-…:step:2:route:1:text', '…:section:base:title'."""
    return f"{service_id}:{kind}:{item_id}:{field}"


def translatable(service_id: str) -> dict[str, dict]:
    """Every text of a service that the citizen can see, keyed by text_key: {key: {"it": ..., "en": ...}}."""
    svc = _services().get(service_id) or {}
    out: dict[str, dict] = {}

    def add(key: str, it: str | None, en: str | None) -> None:
        if it:
            out[key] = {"it": it, "en": en or it}

    for r in svc.get("requirements", []):
        add(text_key(service_id, "req", r["id"]), r.get("text_it"), r.get("text_en"))
        add(text_key(service_id, "req", r["id"], "short"), r.get("short_it"), r.get("short_en"))
    for st in svc.get("steps", []):
        add(text_key(service_id, "step", st["order"]), st.get("text_it"), st.get("text_en"))
        add(text_key(service_id, "step", st["order"], "title"), st.get("title_it"), st.get("title_en"))
        for n, route in enumerate(st.get("routes") or [], start=1):
            add(text_key(service_id, "step", f"{st['order']}:route:{n}"), route.get("text_it"), route.get("text_en"))
    guide = svc.get("form_guide") or {}
    for sec in guide.get("sections", []):
        add(text_key(service_id, "section", sec["id"], "title"), sec.get("title_it"), sec.get("title_en"))
        add(text_key(service_id, "section", sec["id"]), sec.get("text_it"), sec.get("text_en"))
    for h in guide.get("housing_options", []):
        add(text_key(service_id, "housing", h["answer"], "label"), h.get("label_it"), h.get("label_en"))
    return out


def add_runtime_translations(lang: str, texts: dict[str, dict]) -> None:
    """Translations Claude made at runtime for texts the cache doesn't have ({key: {"it", "text"}})."""
    _RUNTIME_TRANSLATIONS.setdefault(lang, {}).update(texts)


def missing_translations(service_id: str, lang: str) -> dict[str, dict]:
    """Texts of a service with no current translation in `lang` (cache or runtime)."""
    if lang in ("it", "en"):
        return {}
    have = {**_translation_file(lang), **_RUNTIME_TRANSLATIONS.get(lang, {})}
    return {k: v for k, v in translatable(service_id).items()
            if not (k in have and have[k].get("it") == v["it"] and have[k].get("text"))}


def localized(service_id: str, kind: str, item_id: object, field: str, it: str | None, en: str | None,
              lang: str) -> tuple[str, bool]:
    """The text in the citizen's language and whether it is Claude's translation.

    Italian and English come from the data. Other languages come from Claude's translation
    when it was made from the current Italian text; otherwise the English text is shown.
    """
    if lang == "it" or not en:
        return (it or en or ""), False
    if lang == "en":
        return en, False
    key = text_key(service_id, kind, item_id, field)
    entry = _RUNTIME_TRANSLATIONS.get(lang, {}).get(key) or _translation_file(lang).get(key)
    if entry and entry.get("it") == it and entry.get("text"):
        return entry["text"], True
    return en, False


def req_text(service_id: str, req: dict, lang: str, field: str = "text") -> tuple[str, bool]:
    """A requirement's text (or its short name, field='short') in the citizen's language."""
    return localized(service_id, "req", req["id"], field, req.get(f"{field}_it"), req.get(f"{field}_en"), lang)


def step_text(service_id: str, step: dict, lang: str, field: str = "text") -> tuple[str, bool]:
    return localized(service_id, "step", step["order"], field, step.get(f"{field}_it"), step.get(f"{field}_en"), lang)


def route_text(service_id: str, step: dict, n: int, lang: str) -> tuple[str, bool]:
    route = (step.get("routes") or [])[n - 1]
    return localized(service_id, "step", f"{step['order']}:route:{n}", "text",
                     route.get("text_it"), route.get("text_en"), lang)


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
    keep = ("id", "municipio", "address", "entrance_note", "entrance_confirmed_by", "phone", "hours_it", "notes_it",
            "booking_without_spid", "nil", "distance_km", "source_id", "data_issues", "dataset_notes")
    return [{k: o[k] for k in keep if k in o} for o in offices[:limit]]


def context_tables() -> dict[str, list[dict]]:
    """City statistics for the panel and the pitch (data/context/*.csv): arrivals from
    abroad, survey results on online services, largest foreign communities."""
    tables = {}
    for path in sorted((DATA / "context").glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as f:
            tables[path.stem] = list(csv.DictReader(f))
    return tables


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
