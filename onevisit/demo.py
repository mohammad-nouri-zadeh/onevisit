"""Demo replay without an API key: the replies are recorded templates, the data is live.

When there is no ANTHROPIC_API_KEY (or the URL has ?demo=1) the app plays a scripted
conversation (the "replay"). Claude's sentences are templates in data/demo/script.json; every fact
in them (service, requirements, offices, source ids) comes from the same tools the
real agent calls (onevisit/tools.py run_tool), computed live on the verified data.
The scripted text never invents a requirement: it points to the checklist, quotes the
verified requirement texts when it lists the urgent options, cites the source ids the
tools returned, and passes the same validator as Claude's live answers.

A message typed in demo mode is understood with keyword rules (`understand`), not by
Claude: the reply says so, and anything the rules can't tell is asked with buttons. The app
signs these replies "OneVisit · replica", never "Claude". Residence words pick one of two
procedures: from abroad, or from another Italian comune / within Milan; when the words don't
say which, the demo asks. The replay writes Italian, English, Arabic, Spanish and Chinese; a
message in another language it recognises (French, Ukrainian, Bengali, Tagalog…) gets an English
reply that names the language and says the live version, with Claude, answers in it.

    from onevisit import demo
    state, user_text, reply = demo.start_persona("cie-isola", "en")
    reply = demo.answer(state, reply["options"][0])
    state, reply = demo.start_text("Ho perso la carta d'identità, abito in Bovisa", "it")
    reply["text"], reply["trace"], reply["check"]

Deep link from the City's booking confirmation email:

    state, reply = demo.start_appointment("carta-identita", "ds549-11", "2026-10-20", "it")

Questions ("quanto costa?", "can my 2-year-old stay home?"), at any time, also in the middle of a
case: the replay answers extractively, with no model. `classify` tells a question from an answer
to the pending deciding question and from the start of a new case; `ask` searches the saved
official pages (the search_official_pages tool, onevisit.search) and replies with a short lead,
the top passages quoted verbatim between « » with their source ids, and, when the pages don't
answer with certainty, says so and links the official page. The case (answers, pending question)
is kept, and the reply offers the pending question again:

    state, reply = demo.respond(None, "Quanto costa la carta d'identità?", "it")
    reply["qa"]["reason"], reply["qa"]["cards"]       # "ok", the passages quoted
    state, reply = demo.respond(state, "Residente a Milano", "it")   # an answer, or a new case
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import pathlib
import re

from onevisit import kb, search, validator
from onevisit.agent import OFFICIAL_HOME, guess_lang
from onevisit.tools import run_tool

DEMO = pathlib.Path(__file__).resolve().parents[1] / "data" / "demo"
LANGS = ("it", "en", "ar", "es", "zh")
SERVICE_CHOICE = "__service__"
# Languages the replay recognises but can't write (agent.guess_lang): named in its English reply.
LANGUAGE_NAMES = {
    "fr": "French (français)", "pt": "Portuguese (português)", "tl": "Tagalog", "uk": "Ukrainian (українська)",
    "ru": "Russian (русский)", "bn": "Bengali (বাংলা)", "hi": "Hindi (हिन्दी)", "ur": "Urdu (اردو)",
    "fa": "Persian (فارسی)", "pa": "Punjabi (ਪੰਜਾਬੀ)", "ta": "Tamil (தமிழ்)", "si": "Sinhala (සිංහල)",
    "am": "Amharic or Tigrinya", "ja": "Japanese (日本語)", "ko": "Korean (한국어)", "th": "Thai (ไทย)",
    "el": "Greek (ελληνικά)", "he": "Hebrew (עברית)",
}


@functools.lru_cache(maxsize=1)
def script() -> dict:
    return json.loads((DEMO / "script.json").read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def personas() -> dict[str, dict]:
    data = json.loads((DEMO / "personas.json").read_text(encoding="utf-8"))
    return {p["id"]: p for p in data["personas"]}


def _lang(lang: str) -> str:
    return lang if lang in LANGS else "en"


def reply_language(text: str, ui_lang: str) -> tuple[str, str | None]:
    """The language the replay answers a typed message in, and the language it saw when it can't write it.

    A message in Italian, English, Arabic, Spanish or Chinese gets a reply in that language; one in a
    language the replay recognises but can't write (French, Ukrainian, Bengali, Tagalog…) gets English
    and that language's code; anything unclear gets the page language."""
    found = guess_lang(text)
    if found in LANGS:
        return found, None
    if found:
        return "en", found
    return _lang(ui_lang), None


def _t(lang: str, key: str, **values: object) -> str:
    templates = script()["templates"]
    return templates.get(_lang(lang), templates["en"]).get(key, templates["en"][key]).format(**values)


def humanize(option_id: str) -> str:
    return option_id.replace("-", " ").replace("_", " ").capitalize()


def option_label(option_id: str, lang: str) -> str:
    """The label of an answer option in the citizen's language."""
    labels = script()["options"].get(option_id, {})
    return labels.get(_lang(lang)) or labels.get("en") or humanize(option_id)


def service_title(service: dict, lang: str) -> str:
    """Service title: Italian or English from the data, other languages from the script."""
    lang = _lang(lang)
    title = service.get("title") or {}
    if lang in ("it", "en"):
        return title.get(lang) or title.get("it") or service.get("id", "")
    return script()["service_titles"].get(service.get("id"), {}).get(lang) or title.get("en") or title.get("it", "")


def question_text(service_id: str, question: dict, lang: str, narrow: dict | None = None) -> str:
    """The deciding question in the citizen's language (Italian and English from the data).

    `narrow` is a narrower form of the question from the data (e.g. "is your rental contract
    already registered?" once the message said the person rents)."""
    lang = _lang(lang)
    asked = narrow or question
    if lang in ("it", "en"):
        return asked.get(f"ask_{lang}") or asked.get("ask_en") or asked.get("ask_it", "")
    key = f"{service_id}.{question['id']}" + (f".{narrow['hint']}" if narrow else "")
    return (script()["questions"].get(key, {}).get(lang)
            or asked.get("ask_en") or asked.get("ask_it", ""))


def narrowed(question: dict, hints: dict | None) -> dict | None:
    """The narrower form of a question that the message's hint selects, if the data has one."""
    hint = (hints or {}).get(question["id"])
    return next((n for n in question.get("narrow") or [] if hint and n.get("hint") == hint), None)


def format_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _cites(ids: list[str]) -> str:
    return " ".join(f"[{s}]" for s in dict.fromkeys(ids))


def _refs(ids: list[str]) -> str:
    """Source ids written as footnote marks right after a word: "fonti ufficiali[cie][ds549]"."""
    return "".join(f"[{s}]" for s in dict.fromkeys(ids))


def _top_sources(reqs: list[dict], k: int = 2) -> list[str]:
    """The sources that back most items: cited in the reply instead of a long row of ids."""
    counts: dict[str, int] = {}
    for r in reqs:
        counts[r["source_id"]] = counts.get(r["source_id"], 0) + 1
    return sorted(counts, key=lambda s: -counts[s])[:k]


@functools.lru_cache(maxsize=1)
def entes() -> dict[str, dict]:
    """The bodies a procedure crosses (data/enti.json): Comune, Questura, Agenzia delle Entrate…"""
    path = DEMO.parent / "enti.json"
    if not path.exists():
        return {}
    return {e["id"]: e for e in json.loads(path.read_text(encoding="utf-8"))}


def ente_name(ente_id: str | None) -> str:
    return (entes().get(ente_id or "") or {}).get("name") or (ente_id or "").replace("-", " ").title()


class _Turn:
    """Runs tools live (exactly as Claude would call them) and records the trace."""

    def __init__(self) -> None:
        self.trace: list[dict] = []

    def call(self, name: str, args: dict) -> object:
        out = json.loads(run_tool(name, args))
        if name == "search_official_pages" and isinstance(out, dict) and "Unknown tool" in str(out.get("error", "")):
            out = json.loads(search.run_tool(args))  # a tools module without the search tool: the same JSON
        self.trace.append({"tool": name, "input": args, "output": out})
        return out


def _questions(service: dict) -> list[dict]:
    return [q for q in service.get("deciding_questions", []) if q.get("options") and q.get("kind") != "date"]


def _next_question(service: dict, checklist: dict, answers: dict) -> dict | None:
    """The first deciding question that still changes the checklist."""
    open_ids = set(checklist.get("still_to_ask", []))
    for q in _questions(service):
        if q["id"] in open_ids and q["id"] not in answers:
            return q
    return None


def _finish(state: dict, turn: _Turn, paragraphs: list[str], options: list[tuple[str, str]] | None = None,
            quotes: bool = False) -> dict:
    """Validate the scripted text like a live answer and build the reply. With `quotes` (a reply that
    quotes the official pages between « »), every quote is checked against the passages the tools
    returned, and the eligibility words are looked for outside the verified quotes only."""
    text = "\n\n".join(p for p in paragraphs if p)
    known = set(kb.sources())
    read = set(state.get("read", [])) | validator.sources_in_trace(turn.trace)
    state["read"] = sorted(read)
    extra: dict = {}
    if quotes and hasattr(validator, "official_texts_in_trace"):
        extra["official_texts"] = validator.official_texts_in_trace(turn.trace)
    reasons = validator.check_reply(text, known_ids=known, read_ids=read,
                                    used_facts=validator.used_facts(turn.trace, text), **extra)
    if options is None:
        q = state.get("pending")
        service = (kb.get_service(state["service_id"]) if state.get("service_id") else None) or {}
        question = next((x for x in _questions(service) if x["id"] == q), None) if q else None
        narrow = narrowed(question, state.get("hints")) if question else None
        ids = (narrow or question or {}).get("options") or []
        options = [(o, option_label(o, state["lang"])) for o in ids]
    return {
        "text": text,
        "options": [label for _, label in options],
        "option_ids": [oid for oid, _ in options],
        "trace": turn.trace,
        "refused": False,
        "demo": True,
        "routing": state.get("routing"),
        "check": {"attempts": 1, "blocked": reasons, "fallback": False, "ok": not reasons},
        "sources_read": sorted(validator.sources_in_trace(turn.trace) & known),
        "cited": validator.cited_source_ids(text, known),
        "lang": state["lang"],
        "other_language": state.get("other_language"),
    }


def _checklist_paragraphs(state: dict, checklist: dict, final: bool) -> list[str]:
    """Say how the checklist changed, citing the main sources of what it holds."""
    lang = state["lang"]
    reqs = checklist.get("requirements", [])
    before = state.get("seen_requirements")
    state["seen_requirements"] = [r["id"] for r in reqs]
    out = []
    n_sources = len({r["source_id"] for r in reqs})
    if not reqs and checklist.get("still_to_ask"):  # nothing yet: the first answers decide everything
        page = (kb.service_links(state["service_id"]).get("official_url") or {}) if state.get("service_id") else {}
        out.append(_t(lang, "need_answers", cites=_refs([page["source_id"]] if page else [])))
    elif not reqs:
        out.append(_t(lang, "none"))
    elif final or before is None:
        out.append(_t(lang, "final" if final else "partial", n=len(reqs), s=n_sources, cites=_refs(_top_sources(reqs))))
        if final:
            out.append(_t(lang, "groups", groups=category_counts(reqs, lang)))
    else:
        added = [r for r in reqs if r["id"] not in set(before)]
        if added:
            out.append(_t(lang, "delta", k=len(added), n=len(reqs), cites=_refs(_top_sources(added, 3))))
        else:
            out.append(_t(lang, "same", n=len(reqs), cites=_refs(_top_sources(reqs))))
    todo = checklist.get("not_yet_verified", [])
    if final and todo:
        out.append(_t(lang, "todo_1") if len(todo) == 1 else _t(lang, "todo", m=len(todo)))
    return out


def category_label(category: str, lang: str) -> str:
    """Name of a checklist group (prepare, how, if-urgent, after) in the citizen's language."""
    labels = script()["categories"].get(category, {})
    return labels.get(_lang(lang)) or labels.get("en") or humanize(category)


def category_counts(reqs: list[dict], lang: str) -> str:
    """"14 da preparare, 6 su come funziona…": how the checklist is grouped, counted live."""
    counts: dict[str, int] = {}
    for r in reqs:
        counts[r.get("category") or "prepare"] = counts.get(r.get("category") or "prepare", 0) + 1
    order = [c for c in kb.CATEGORIES if c in counts] + [c for c in counts if c not in kb.CATEGORIES]
    sep = "، " if _lang(lang) == "ar" else ("、" if _lang(lang) == "zh" else ", ")
    return sep.join(_t(lang, "group_count", k=counts[c], group=category_label(c, lang)) for c in order)


def urgent_items(checklist: dict) -> list[dict]:
    """The fastest routes the sources give for this case (items marked urgent_lead in the data:
    walk-in exceptions first, then the urgent-only options such as the temporary card)."""
    reqs = checklist.get("requirements", [])
    lead = [r for r in reqs if r.get("urgent_lead")]
    return sorted(lead, key=lambda r: r.get("category") == "if-urgent")


def _urgent_paragraphs(state: dict, checklist: dict) -> list[str]:
    """For someone in a hurry: the verified urgent options, each as written in the data, with its source."""
    items = urgent_items(checklist)
    if not items:
        return []
    lang = state["lang"]
    lines = [f"- {kb.req_text(state['service_id'], r, lang)[0]} [{r['source_id']}]" for r in items]
    return [_t(lang, "urgent_intro") + "\n" + "\n".join(lines)]


def routes(service: dict, answers: dict) -> list[dict]:
    """The routes the data attaches to the answers so far (`option_routes` of the deciding questions):
    "stop" (this person cannot apply here: no booking link, no desk dossier, the services to do first),
    "home" (home service: its online form instead of the booking page), "info" (no visit needed),
    "walk-in", plus booking links of their own (e.g. the PIN/PUK duplicate), each with its source."""
    if service.get("id"):  # the catalog's own rule: a stop only while something it stops is still possible
        return kb.active_routes(service["id"], answers)
    out = []
    for q in service.get("deciding_questions", []):
        route = (q.get("option_routes") or {}).get(answers.get(q["id"]))
        if route:
            out.append(route)
    return out


# When several routes apply, the one that decides how the case is sent: a stop ends it, the home
# service replaces the desk, a question needs no visit, the PIN/PUK desk has its own booking.
ROUTE_PRIORITY = ("stop", "home", "info", "desk", "walk-in")


def case_route(service_id: str | None, answers: dict | None) -> dict:
    """How this case is sent, from the data (the deciding questions' `option_routes` and the service links).

    {"kind", "links", "services", "booking"}: kind is "stop" (not served here: no booking, `services`
    lists what to do first, each {"id", "title", "url", "source_id"}), "home" (the home-service form in
    `links`), "info" (no visit needed), "desk" (a desk visit with booking links of its own, e.g. the
    PIN/PUK duplicate, in `links`), "walk-in" (no appointment), "online" (the City's or ANPR's online
    form) or "booking" (the service's own booking page); "none" when the data says nothing. `booking`
    is True only when the service's booking page is the next step."""
    service = (kb.get_service(service_id) if service_id else None) or {}
    answers = answers or {}
    found = routes(service, answers)
    kinds = [r.get("route") for r in found]
    links = service.get("links") or {}
    kind = next((k for k in ROUTE_PRIORITY if k in kinds), None)
    own = [link for r in found if r.get("route") == kind for link in r.get("links", [])
           if link.get("url") and link.get("source_id")]
    if kind == "desk" and not own:
        kind = None
    if kind is None:
        kind = "online" if links.get("online_form_url") else ("booking" if links.get("booking_url") else "none")
    services = []
    if kind == "stop":
        wanted = [s["id"] for r in found if r.get("route") == "stop" for s in r.get("services", [])
                  if all(answers.get(q) in allowed for q, allowed in (s.get("when") or {}).items())]
        for sid in dict.fromkeys(wanted):
            other = kb.get_service(sid) or {}
            page = kb.service_links(sid).get("official_url")
            if page:
                services.append({"id": sid, "title": other.get("title") or {}, "url": page["url"],
                                 "source_id": page["source_id"]})
    return {"kind": kind, "links": own if kind in ("home", "desk") else [], "services": services,
            "booking": kind == "booking"}


def link_label(link: dict, lang: str) -> str:
    """Label of a route link in the citizen's language (script.json, else the data's Italian/English)."""
    lang = _lang(lang)
    labels = script().get("links", {}).get(link.get("id"), {})
    return labels.get(lang) or link.get(f"label_{lang}") or link.get("label_en") or link["url"]


def _stop_paragraphs(state: dict, turn: _Turn, found: list[dict], checklist: dict) -> list[str]:
    """This person cannot apply here: say so with the sources of the items, and link the services to do first."""
    lang = state["lang"]
    out = [_t(lang, "stop", cites=_refs(_top_sources(checklist.get("requirements", []))))]
    services = []
    answers = state["answers"]
    wanted = [s["id"] for r in found for s in r.get("services", [])  # each service with its own condition
              if all(answers.get(q) in allowed for q, allowed in (s.get("when") or {}).items())]
    for sid in dict.fromkeys(wanted):
        other = turn.call("get_service", {"service_id": sid})
        link = ((other.get("links") or {}).get("official_url") if isinstance(other, dict) else None)
        if link:
            services.append(f"[{service_title(other, lang)}]({link['url']}) [{link['source_id']}]")
    if services:
        out.append(_t(lang, "stop_services", services=" · ".join(services)))
    return out


_ROUTE_DOSSIER = {"home": "dossier_home", "info": "dossier_info", "walk-in": "dossier_walkin"}


def _urgent_first(state: dict, turn: _Turn, service: dict) -> list[str]:
    """First reply to someone in a hurry: the urgent routes for the usual case of the answers still
    missing (script.json "urgent_assume", e.g. resident in Milan and able to come to the desk), said
    as a condition; the questions follow. Called before the real get_checklist, so the case keeps
    the citizen's own answers."""
    assume = [a for a in script().get("urgent_assume", {}).get(service["id"], [])
              if a["question"] not in state["answers"]]
    if not state.get("urgent") or state.get("urgent_shown") or not assume:
        return []
    probe = turn.call("get_checklist", {"service_id": service["id"],
                                        "answers": {**state["answers"], **{a["question"]: a["option"] for a in assume}}})
    items = urgent_items(probe) if isinstance(probe, dict) else []
    if not items:
        return []
    state["urgent_shown"] = True
    lang = state["lang"]
    assumed = _t(lang, "and_join").join(a["label"].get(lang) or a["label"]["en"] for a in assume)
    lines = [f"- {kb.req_text(state['service_id'], r, lang)[0]} [{r['source_id']}]" for r in items]
    return [_t(lang, "urgent_intro_if", assumed=assumed) + "\n" + "\n".join(lines)]


def _urgent_once(state: dict, checklist: dict) -> list[str]:
    """For someone in a hurry, the urgent routes once, when no question is left: which routes apply
    depends on the answers (where the person is resident, whether they can come to the desk)."""
    if not state.get("urgent") or state.get("urgent_shown") or checklist.get("still_to_ask"):
        return []
    out = _urgent_paragraphs(state, checklist)
    state["urgent_shown"] = bool(out)
    return out


def _ask_or_finish(state: dict, turn: _Turn, service: dict, checklist: dict, first: bool) -> list[str]:
    lang = state["lang"]
    question = _next_question(service, checklist, state["answers"])
    if question:
        state["pending"] = question["id"]
        return _checklist_paragraphs(state, checklist, final=False) + [
            _t(lang, "ask_first" if first else "ask_next",
               question=question_text(service["id"], question, lang, narrowed(question, state.get("hints"))))]
    state["pending"] = None
    state["done"] = True
    paragraphs = _checklist_paragraphs(state, checklist, final=True)
    found = routes(service, state["answers"])
    kinds = [r.get("route") for r in found]
    if "stop" in kinds:
        return paragraphs + _stop_paragraphs(state, turn, found, checklist)
    own_links = [link for r in found for link in r.get("links", [])]
    if own_links:
        paragraphs.append(_t(lang, "route_links", links=" · ".join(
            f"[{link_label(link, lang)}]({link['url']}) [{link['source_id']}]" for link in own_links)))
    links = service.get("links") or {}  # from get_service, each link with the saved source that has it
    online = links.get("online_form_url")
    if online:
        kind = service.get("online_form_kind")
        key = f"online_{kind}" if kind and f"online_{kind}" in script()["templates"]["en"] else "online"
        paragraphs.append(_t(lang, key, url=online["url"], cite=f"[{online['source_id']}]"))
        if service.get("has_form_guide"):
            guide = turn.call("get_form_guide", {"service_id": service["id"], "answers": dict(state["answers"])})
            sections = guide.get("sections", []) if isinstance(guide, dict) else []
            cite = next((s["source_id"] for s in sections if s.get("id") not in ("dichiarazione", "invio")), None)
            if cite:
                paragraphs.append(_t(lang, "form_guide", cite=f"[{cite}]"))
    booked_at_desk = "prenotazione" in {x.get("id") for x in checklist.get("sources", []) if x}
    if booked_at_desk and not online and not state.get("date"):  # from a booking link the appointment exists
        booking = links.get("booking_url")
        if booking:
            paragraphs.append(_t(lang, "booking", url=booking["url"], cite=f"[{booking['source_id']}]"))
        else:
            page = turn.call("get_source", {"source_id": "prenotazione"})
            if isinstance(page, dict) and page.get("url"):
                paragraphs.append(_t(lang, "booking", url=page["url"], cite="[prenotazione]"))
    kind = service.get("online_form_kind")
    own = f"dossier_{kind}" if online and kind and f"dossier_{kind}" in script()["templates"]["en"] else None
    route = next((_ROUTE_DOSSIER[k] for k in kinds if k in _ROUTE_DOSSIER), None)
    paragraphs.append(_t(lang, own or route or ("dossier_online" if online else "dossier")))
    return paragraphs


def _steps_line(lang: str, service: dict) -> list[str]:
    """When the path crosses several bodies (Questura, Agenzia delle Entrate, Comune), say so and cite."""
    steps = service.get("steps") or []
    bodies = list(dict.fromkeys(b for s in steps for b in [s.get("ente")] + [r.get("ente") for r in s.get("routes") or []] if b))
    if len(bodies) < 2:
        return []
    return [_t(lang, "steps", n=len(steps), entes=", ".join(ente_name(b) for b in bodies),
               cites=_cites(_top_sources([s for s in steps if s.get("source_id")], 2)))]


def office_where(office: dict) -> str:
    """Address of an office with its entrance note, e.g. via Larga 12 (Ingresso da via Pecorari 3)."""
    return office["address"] + (f" ({office['entrance_note']})" if office.get("entrance_note") else "")


def _office_line(state: dict, office: dict, area: str) -> str:
    cites = [office.get("source_id", "ds549")] + ([office["entrance_confirmed_by"]["source_id"]]
                                                  if office.get("entrance_confirmed_by") else [])
    return _t(state["lang"], "office", area=area, office=office_where(office), office_cite=_cites(cites))


def new_state(service_id: str | None, lang: str, **extra: object) -> dict:
    return {"service_id": service_id, "lang": _lang(lang), "answers": {}, "pending": None,
            "done": False, "read": [], "office_id": None, "date": None, "checklist": None,
            "offices": None, "urgent": False, "routing": None, "hints": {}, **extra}


def _begin(state: dict, turn: _Turn, answers: dict, area_query: str | None, area_label: str | None) -> list[str]:
    """First reply for a known service: read it, apply what the message already says, find the office,
    lead with the urgent options when the person is in a hurry, then ask or finish."""
    lang = state["lang"]
    turn.call("list_services", {})
    service = turn.call("get_service", {"service_id": state["service_id"]})
    if not isinstance(service, dict) or "error" in service:
        return [_t(lang, "none")]
    live_q = {q["id"]: q for q in _questions(service)}
    hints = dict(state.get("hints") or {})
    answers = {k: _alias(v, live_q[k]["options"]) for k, v in answers.items() if k in live_q}
    for qid, hint in list(hints.items()):  # "I rent" is enough for a service that only asks owner or not
        if qid in live_q and qid not in answers and _alias(hint, live_q[qid]["options"]) in live_q[qid]["options"] \
                and not narrowed(live_q[qid], hints):
            answers[qid] = _alias(hint, live_q[qid]["options"])
    state["answers"] = {k: v for k, v in answers.items() if v in live_q[k]["options"]}
    urgent = _urgent_first(state, turn, service)
    checklist = turn.call("get_checklist", {"service_id": service["id"], "answers": dict(state["answers"])})
    state["checklist"] = checklist
    paragraphs = [_t(lang, "opening", service=service_title(service, lang))]
    paragraphs += _steps_line(lang, service)
    if state["answers"]:
        facts = ", ".join(option_label(v, lang) for v in state["answers"].values())
        paragraphs.append(_t(lang, "understood", facts=facts))
    paragraphs += urgent or _urgent_once(state, checklist)
    if area_query:
        offices = turn.call("find_offices", {"area": area_query, "limit": 2})
        if isinstance(offices, list) and offices:
            state["offices"] = offices
            state["office_id"] = offices[0]["id"]
            paragraphs.append(_office_line(state, offices[0], area_label or area_query))
    paragraphs += _ask_or_finish(state, turn, service, checklist, first=True)
    return paragraphs


# One service may word an answer more broadly than another: for a change of residence from another
# comune the only housing question is "is the home yours?", so renting, guest and the like are "no".
_ALIASES = {"non-proprietario": ("affitto", "affitto-registrato", "affitto-erp", "comodato", "ospite",
                                 "lavoro-domestico")}


def _alias(value: str, options: list[str]) -> str:
    """The service's own option for an answer read from the message (e.g. affitto -> non-proprietario)."""
    if value in options:
        return value
    return next((o for o in options if value in _ALIASES.get(o, ())), value)


def start_persona(persona_id: str, lang: str) -> tuple[dict, str, dict]:
    """First turn of a persona demo: returns the state, what the persona writes, and the reply."""
    persona = personas()[persona_id]
    lang = _lang(lang)
    state = new_state(persona["service_id"], lang, persona=persona_id, urgent=bool(persona.get("urgent")),
                      hints=dict(persona.get("hints") or {}))
    user_text = persona["opening"].get(lang) or persona["opening"]["en"]
    turn = _Turn()
    area = (persona.get("area") or {}).get(lang) or (persona.get("area") or {}).get("en")
    paragraphs = _begin(state, turn, persona.get("inferred", {}), persona.get("area_query"), area)
    return state, user_text, _finish(state, turn, paragraphs)


# ---------- typed text in demo mode: keyword rules, not Claude ----------
@functools.lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(validator.fold(pattern))  # folded like the text: lower case, no accents, bare Arabic letters


def _any(patterns: tuple[str, ...], text: str) -> bool:
    """True if any pattern matches the folded text."""
    return any(_compiled(p).search(text) for p in patterns)


# "iscrizione-anagrafica-extra-ue" holds the residence words in general: `understand` then picks
# between residence from abroad and a change of residence from another comune.
_SERVICE_WORDS = {
    "carta-identita": (r"carta d'?\s?identita", r"carta di identita", r"\bidentity card", r"\bid card", r"\bcie\b",
                       r"carte d'identite", r"carta de identidad", r"documento de identidad", r"\bdni\b", "身份证",
                       "身份證", "بطاقة الهوية", "بطاقة هوية", "هويتي", r"carteira de identidade"),
    "iscrizione-anagrafica-extra-ue": (r"\bresidenz", r"\bresidence\b(?!\s+permit)", r"\bresiden(cia|te)",
                                       r"\bregister\b", r"\bregistr(ar|arme|amos|iamo)", r"\banagrafe\b",
                                       r"\biscrizione anagrafica", r"\bempadron", "居住登记", "户籍", "登记居住", "落户",
                                       "تسجيل الإقامة", "أسجّل إقامتي", "أسجل إقامتي", "نسجّل إقامتنا", "تسجيل إقامتي",
                                       r"\binscricao de residencia", r"\bdomicil", r"\binscri(?:re|ption)\b",
                                       r"\bm'inscrire\b"),
}
_ANSWER_WORDS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "motivo": [
        ("smarrimento-furto", (r"\bpers[oa]\b", r"\bsmarrit", r"\brubat", r"\bfurto\b", r"\blost\b", r"\bstolen\b",
                               r"\bperdi\b", r"\bperdido", r"\brobad", r"\brobo\b", r"\bperdu", r"\bvolee?s?\b", "丢", "被偷",
                               "遗失", "فقدت", "ضاعت", "ضاع", "سرق", "سُرقت")),
        # a damaged card (physical damage words) before a chip-only fault; "broken" alone could be either
        ("deteriorata", (r"\brovinat", r"\bdeteriorat", r"\bdanneggiat", r"\bdamaged", r"\bestropead",
                         r"\bdanad[ao]\b", r"\babimee?\b", r"\bendommag", "损坏", "تالفة", "تالف")),
        ("chip", (r"\bchip\b", r"\bpuce\b", "芯片", "الشريحة")),
        ("deteriorata", (r"\brott[ao]\b", r"\bbroken\b", r"\brot[ao]\b", "坏了")),
        # already has the card: a change of address or marital status, a card that has not arrived
        ("gia-cie", (r"\bcambiat\w* (l'?\s?)?(indirizzo|residenza|stato civile)", r"\bcambio (di |d'?\s?)?indirizzo",
                     r"\bchanged? (my )?(address|marital status)", r"\bmoved (house|flat)",
                     r"\bnon (mi )?e (ancora )?arrivat", r"\bnot (yet )?arrived", r"\bhas ?n'?t (yet )?arrived",
                     r"\bno (me )?ha llegado", r"\bcambiado de (direccion|domicilio)", "没有收到", "还没收到", "更改地址",
                     "لم تصل", "غيرت عنواني")),
        ("rinnovo", (r"\bscadut", r"\bscade\b", r"\brinnov", r"\bexpir", r"\brenew", r"\bcaduc", r"\brenov", r"\bvencid",
                     r"\bcartacea", r"\bpaper (id|identity|card)", r"\brenouvel", "过期", "到期", "更新", "انتهت",
                     "منتهية", "تجديد")),
        ("prima", (r"\bprima carta", r"\bper la prima volta", r"\bfirst (italian )?(id|identity)",
                   r"\bfor the first time", r"\bprimera (carta|vez)", r"\bpor primera vez", "第一次", "首次",
                   "أول بطاقة")),
    ],
    "cittadinanza": [
        ("italiana", (r"\b(sono|i'?m|i am|soy|je suis|sou)\s+([a-z]+\s+(e|and|y)\s+)?italian", r"\bcittadin[oa] italian",
                      "أنا إيطالي",
                      "我是意大利人")),
        ("extra-ue", (r"\begypt", r"\begitt", r"\begipt", r"\bcairo\b", "مصر", "القاهرة", "埃及", r"\bchin[ae]\b",
                      r"\bcines[ei]\b", r"\bchinese\b", r"\bchino\b", "中国", r"\bper[uú]\b", r"\bperuvian", r"\bperuan",
                      "البيرو", "秘鲁", r"\bphilippin", r"\bfilippin", r"\bfilipin", r"\bsri lanka", r"\bindia", r"\bmoroc",
                      r"\bmarocc", r"\bmarruec", "المغرب", r"\bbangladesh", r"\bpakistan", r"\bnigeria", r"\bbrazil",
                      r"\bbrasil", r"\bcolombia", r"\becuador", r"\balbani", r"\bukrain", r"\bucrain", r"\bsenegal",
                      r"\btunisi", r"\bextra[- ]?ue\b", r"\bnon[- ]eu\b", r"\boutside the eu\b",
                      r"\bfuori (dall'?\s?)?ue\b", r"\bextracomunitar", r"\bmaroc\b", r"\balgeri",
                      r"\bcote d'?ivoire", r"\bcameroun", r"\bhors (de l')?ue\b",
                      # only non-EU citizens hold a permesso di soggiorno
                      r"\bpermesso di soggiorno", r"\bresidence permit", r"\bpermiso de residencia",
                      r"\btitre de sejour", "居留许可", "تصريح إقامة", "تصريح الإقامة")),
        ("ue", (r"\bromani", r"\brumen", r"\bpolon", r"\bpoland", r"\bpolacc", r"\bpolish\b", r"\bfranc[ei]",
                r"\bfrench\b", r"\bspagn", r"\bspain", r"\bspanish\b", r"\bgermani", r"\btedesc", r"\bgerman\b",
                r"\bcittadin[oa] (ue|europe)", r"\beu citizen")),
    ],
    # Where the person is registered as resident (ID card): only explicit residence words count;
    # "I live in Isola" says where they live, not where they are registered, so it stays a question.
    "residenza": [
        ("aire", (r"\baire\b",)),
        ("non-residente", (r"\bnon (sono |e |siamo )?(ancora )?resident", r"\bnon ho (ancora )?(la )?residenza",
                           r"\bsenza residenza", r"\bnot (yet )?(registered as )?(a )?resident",
                           r"\bnot (yet )?registered as", r"\bno (tengo|tiene) (la )?residencia", r"\bsin residencia",
                           r"\bno estoy empadronad", r"\bsans residence", "还没有登记居住", "没有居住登记", "尚未登记居住",
                           "لست مسجلا", "لم أسجل إقامتي", "غير مسجل كمقيم")),
        ("altro-comune-lombardia", (r"\bresiden\w*\s+(a|in|en|à)\s+(monza|bergamo|brescia|como|pavia|varese|lecco|lodi|"
                                    r"cremona|mantova|sondrio|sesto san giovanni|cinisello|rho|legnano|busto arsizio|"
                                    r"gallarate|saronno|seregno|desio|lissone|vigevano|abbiategrasso|cologno monzese|"
                                    r"san donato milanese|rozzano|corsico|paderno dugnano|segrate|bollate)\b",
                                    r"\b(altro|un altro) comune (della |in )?lombardia",
                                    r"\banother (comune|town|city) in lombardy")),
        # resident outside Lombardy: domicilio-milano or altra-regione, decided in understand (_OUTSIDE_LOMBARDY)
        ("domicilio-milano", (r"\bdomicili\w* a milano", r"\bdomiciled in milan")),
        ("milano", (r"\bresiden\w*\s+(a|in|en|à)\s+milan", r"\bregistered (as a )?residents? (in|of) milan",
                    r"\bempadronad[oa] en milan", "户籍在米兰", "在米兰登记居住", "مقيم في ميلانو", "مسجل في ميلانو")),
    ],
    # Only someone who cannot move for serious health reasons gets the home service (ID card).
    "presenza": [
        ("domicilio-salute", (r"\ballettat", r"\bbedridden", r"\bbed-?bound", r"\bricoverat", r"\bin ospedale",
                              r"\bin (a |the )?hospital", r"\bcare home", r"\bnursing home", r"\brsa\b",
                              r"\bnon (puo|posso|riesce a|riesco a) (muover|camminar|uscire di casa)",
                              r"\bcannot (move|walk)", r"\bcan[’']?t (move|walk)",
                              r"\bencamad", r"\bhospitalizad", r"\ben (el )?hospital", r"\bno puede (moverse|caminar)",
                              r"\b(costrett|bloccat)[oa] a letto", r"\ba letto\b",
                              "卧床", "住院", "不能行动", "طريح الفراش", "في المستشفى", "لا يستطيع الحركة")),
    ],
    "permesso": [
        ("altro", ()),  # student waiting for a first study permit: see _infer
        ("ricevuta-famiglia", (r"\bricongiung", r"\breunific", r"\breagrupa", "团聚", "لم شمل", "لمّ شمل")),
        ("ricevuta-rinnovo", (r"\brinnovo del permesso", r"\brenew(al|ing)? (of )?my (residence )?permit",
                              r"\brenovacion del permiso", "续签", "تجديد تصريح")),
        ("nessuno", (r"\bnot applied", r"\bhaven'?t applied", r"\bnon l'?ho ancora chiesto", r"\bnon ho ancora chiesto",
                     r"\bno (lo )?he pedido", "还没有申请", "لم أقدم", "لم أطلب")),
        ("permesso", (r"\bho (gia )?(il|un) permesso", r"\b(i have|i've got|with) (a |my )?(residence )?permit",
                      r"\btengo (mi |el |un )?permiso", r"\bcon (mi |el )?permiso", r"\bcom o meu permesso",
                      "有居留许可", "有居留证", "لدي تصريح إقامة", "معي تصريح")),
    ],
    "famiglia": [
        ("con-familiari", (r"\bcon (mia|mio|i miei|le mie|la mia|il mio) (moglie|marito|figli|famiglia|bambin)",
                           r"\bmia moglie\b", r"\bmio marito\b", r"\bwith my (wife|husband|children|kids|family|son|daughter)",
                           r"\bmy wife\b", r"\bmy husband\b", r"\bcon mi (esposa|esposo|marido|familia|hij)",
                           r"\bmi esposa\b", r"\bcon mis hijos", "和家人", "跟家人", "妻子", "丈夫", "مع عائلتي", "مع زوجي",
                           "مع زوجتي", "مع أطفالي", r"\bcom (a minha|o meu|meus) (esposa|marido|familia|filhos)",
                           r"\bavec (ma|mon|mes) (femme|mari|enfants?|famille|fils|fille)")),
        ("solo", (r"\bda sol[oa]\b", r"\balone\b", r"\bby myself", r"\bsozinh", r"\bseule?\b", "一个人", "独自",
                  "وحدي", "بمفردي")),
    ],
    "alloggio": [
        ("affitto-erp", (r"\bcasa popolare", r"\bcase popolari", r"\berp\b", r"\bpublic housing", r"\bvivienda social")),
        ("comodato", (r"\bcomodato",)),
        ("lavoro-domestico", (r"\bcolf\b", r"\bbadante", r"\bdomestic worker", r"\bcarer\b", r"\bcuidador",
                              r"\bempleada de hogar", "保姆", "عاملة منزلية")),
        ("ospite", (r"\bospite\b", r"\bguest\b", r"\binvitad", r"\bhosted\b", r"\bfriend'?s (flat|house|place)",
                    r"\bheberge",
                    "借住", "ضيف")),
        ("proprieta", (r"\bproprietari", r"\bproprietaire", r"\bi own\b", r"\bmy own (flat|apartment|house)",
                       r"\bpropietari",
                       "自己的房子", "أملك")),
    ],
}
# Renting: whether the contract is already registered changes the file to upload, so the words
# must say it; "I rent a room" alone leaves a hint and the demo asks the narrower question.
_RENT = (r"\baffitt", r"\brent", r"\balquil", r"\barriend", "租", "إيجار", "أستأجر", "نستأجر", "مستأجر",
         r"\bloue\b", r"\balug")
_NOT_REGISTERED = (r"\bnon (e |ancora |e ancora )?registrat", r"\bin (corso di )?registrazione", r"\bnot (yet )?registered",
                   r"\bunregistered", r"\bno (esta )?registrad", r"\bsin registrar", r"\bpas (encore )?enregistre",
                   "未登记", "没有登记", "غير مسجل")
_REGISTERED = (r"\bregistrat[oa]\b", r"\bregistered\b", r"\bregistrad[oa]\b", r"\benregistre", "已登记", "مسجل")

# Which residence procedure: from abroad (the City's online form for non-EU citizens) or from another
# Italian comune / within Milan (the national ANPR website). Only explicit words count.
_ITALIAN_PLACES = ("torino", "turin", "roma", "rome", "napoli", "naples", "bologna", "firenze", "florence", "genova",
                   "genoa", "venezia", "venice", "verona", "padova", "padua", "trieste", "trento", "bolzano", "brescia",
                   "bergamo", "monza", "pavia", "varese", "lecco", "lodi", "cremona", "mantova", "sondrio",
                   "parma", "modena", "reggio", "piacenza", "rimini", "ferrara", "perugia", "ancona", "pescara",
                   "bari", "lecce", "taranto", "salerno", "palermo", "catania", "messina", "cagliari", "sassari",
                   "novara", "alessandria", "cuneo", "aosta", "piemonte", "lombardia", "veneto", "liguria", "toscana",
                   "emilia", "lazio", "campania", "puglia", "calabria", "sicilia", "sardegna", "abruzzo", "marche",
                   "umbria", "basilicata", "molise", "friuli")
_FROM_PLACE = re.compile(r"\b(?:da|dal|dalla|from|desde|de)\s+(?:" + "|".join(_ITALIAN_PLACES) + r")\b")
_INTERNAL = (r"\b(?:da|dal) (?:un )?altro comune", r"\baltro comune italiano", r"\bcambio (?:di |d')?indirizzo",
             r"\bcambiare indirizzo", r"\bcambiato (?:casa|indirizzo)", r"\bdentro milano", r"\ball'?interno di milano",
             r"\bchange (?:of )?address", r"\bwithin milan", r"\bfrom another (?:italian )?(?:city|town|municipality|comune)",
             r"\b(?:another|other) (?:city|town|municipality) in italy", r"\bfrom elsewhere in italy",
             r"\bcambio de (?:domicilio|direccion)", r"\bde otro (?:municipio|ayuntamiento)", r"\baire\b",
             r"\bchangement d'adresse", r"\bd'une autre (?:ville|commune)",
             r"\b(?:da|from) como\b",
             "从意大利其他城市", "换地址", "من مدينة إيطالية أخرى", "تغيير العنوان",
             *(f"من {c}" for c in ("تورينو", "روما", "نابولي", "بولونيا", "فلورنسا", "جنوة", "البندقية", "باليرمو")),
             *(f"从{c}" for c in ("都灵", "罗马", "那不勒斯", "博洛尼亚", "佛罗伦萨", "热那亚", "威尼斯", "巴勒莫")))
_ABROAD = (r"\bdall'?\s?estero", r"\bfrom abroad", r"\bdel extranjero", r"\bdesde el extranjero",
           r"\barriv\w* in italia", r"\barrived in (?:italy|milan)", r"\bjust arrived", r"\bappena arrivat",
           r"\bnew to italy", r"\bpermesso di soggiorno", r"\bresidence permit", r"\bpermiso de (?:residencia|estudio)",
           r"\bstudy permit", r"\bvisto\b", r"\bvisa\b", r"\b(?:titre|carte|permis) de sejour", r"\bde l'etranger",
           r"\bje viens d'arriver", r"\barrivee? en italie", "居留", "签证", "从国外", "تصريح", "تأشيرة", "من الخارج")
_STUDY = (r"\bstudi", r"\bstudent", r"\bestudi", r"\betudi", r"\buniversit", "留学", "学生", "学习", "دراسة", "للدراسة",
          "طالب")
_WAITING = (r"\baspett", r"\bwait", r"\bespero", r"\besperando", r"\battend", r"\bpremier titre", r"\bprimo permesso",
            r"\bfirst (residence )?permit",
            r"\bprimer permiso", "等", "أنتظر", "انتظار", "أول تصريح")
_CHILD = (r"\bfigli[oa]\b", r"\bbambin", r"\bmy (son|daughter|child)", r"\bfor my (son|daughter|child)", r"\bhij[oa]\b",
          r"\bmenor\b", r"\bminorenn", r"\bmon (fils|enfant)", r"\bma fille", "孩子", "儿子", "女儿", "ابني", "ابنتي", "طفلي")
_FIRST_PERSON = (r"\b(ho|sono|mia|mio|i|my|me|yo|mi|tengo|je|ma|mon|eu|meu|minha)\b", "我", "أنا", "فقدت", "هويتي",
                 "بطاقتي", "لدي")
_URGENT = (r"\bparto\b", r"\bparti\b", r"\bpartenza", r"\bviaggi", r"\btravel", r"\btrip\b", r"\bflight", r"\bviaj",
           r"\burgen", r"\bentro \d+ giorni", r"\bwithin \d+ days", r"\bnext (week|month)", r"\bmese prossimo",
           r"\bsettimana prossima", r"\bmes que viene", r"\bproximo mes", r"\bvoyage", r"\bje pars\b",
           r"\bmois prochain", r"\bsemaine prochaine", "出行", "旅行", "出国", "下个月",
           "急", "سأسافر", "سفر", "مستعجل", "عاجل", "الشهر القادم")


@functools.lru_cache(maxsize=1)
def _areas() -> list[tuple[str, str]]:
    """Neighbourhood and street names of the registry offices (ds549), folded, longest first."""
    names: set[str] = set()
    for o in kb.find_offices(limit=1000):
        for part in re.split(r"\s*-\s*", o["nil"]["name"]):
            part = re.sub(r"^Q\.?RE\s+", "", part.strip(), flags=re.IGNORECASE)
            if len(part) >= 4:
                names.add(part.title())
        street = re.sub(r"^(via|viale|piazza|piazzale|largo)\s+", "", o["address"], flags=re.IGNORECASE)
        street = re.sub(r"\s+\d+.*$", "", street)
        if len(street) >= 4:
            names.add(street)
    aliases = {"إيزولا": "Isola", "بوفيزا": "Bovisa", "بادوفا": "Padova"}
    return sorted([(validator.fold(n), n) for n in names] + [(validator.fold(k), v) for k, v in aliases.items()],
                  key=lambda x: -len(x[0]))


# Words that change what the motivo and citizenship rules may read (see understand). _PIN and _CARD_LOST
# are folded like the text (lower case), so they avoid upper-case classes such as \S.
_PERMIT_RENEWAL = re.compile(r"\b(?:permesso|permit|permiso|titre)\b(?:\s+\S+){0,4}?\s+(?:in\s+|under\s+|en\s+)?"
                             r"(?:rinnov|renew|renov)\w*|\b(?:rinnovo|renewal|renovacion)\s+(?:del|of the|of my|of|de)\s+"
                             r"(?:mio\s+|su\s+|mi\s+)?(?:permesso|permit|permiso)")
_PLACE = re.compile(r"\b(?:in|a|en|nel|nella|negli|to|at|au|aux|dans)\s+(?:\w+\s+)?(?:spagna|spain|espana|francia|"
                    r"france|germania|germany|alemania|polonia|poland|romania|egitto|egypt|egipto|cina|china|peru|"
                    r"marocco|morocco|marruecos|maroc|india|albania|ucraina|ukraine|tunisia|senegal|brasile|brazil|"
                    r"brasil|filippine|philippines|filipinas|bangladesh|pakistan|nigeria|colombia|ecuador|sri lanka|"
                    r"europa|europe|estero|abroad)\b")
# Resident in a comune outside Lombardy: Milan issues the card only to someone who lives in Milan
# (domicilio-milano); someone who doesn't is "altra-regione" (a stop). The words must say which: living in
# Milan (or a Milan neighbourhood named) or not; otherwise the residence question stays open, with buttons.
_OUTSIDE_LOMBARDY = (r"\bresiden\w* fuori (dalla )?(lombardia|regione)", r"\bresident outside lombardy",
                     r"\bresiden\w*\s+(a|in|en|à)\s+(torino|turin|roma|rome|napoli|naples|bologna|firenze|florence|"
                     r"genova|genoa|venezia|venice|verona|padova|padua|trieste|trento|bolzano|parma|modena|"
                     r"palermo|catania|bari|cagliari|perugia|ancona|pescara|aosta)\b")
_LIVES_IN_MILAN = (r"\b(abito|vivo|viviamo|abitiamo|sto|stiamo|domiciliat\w*|lavoro|studio) (a|in) milano",
                   r"\b(i |we )?(live|living|stay|staying|work|study) in milan", r"\b(vivo|vivimos) en milan",
                   r"\bj'?\s?habite a milan", "住在米兰", "أعيش في ميلانو", "أسكن في ميلانو")
_NOT_IN_MILAN = (r"\bnon (abito|vivo|sto|abitiamo|viviamo) (a|in) milano", r"\b(don'?t|do not|doesn'?t) live in milan",
                 r"\bnot living in milan", r"\bno vivo en milan", "不住在米兰", "لا أسكن في ميلانو", "لا أعيش في ميلانو")
# Lost, stolen or expired: of another document than the card ("ho perso la tessera sanitaria", "mi pasaporte
# está vencido", "il permesso scaduto"), when no card noun stands between the word and that document. Such a
# phrase says nothing about why the card is needed: the motivo rules don't read it.
_CARD_NOUN = r"(?:carta|card|cie|carte|tarjeta|dni)\b"
_OTHER_DOC = (r"(?:tessera sanitaria|health card|tarjeta sanitaria|codice fiscale|passaport\w*|passport\w*|pasaporte\w*|"
              r"passeport\w*|permesso(?: di soggiorno)?|permit|permiso(?: de residencia)?|titre de sejour|patente|"
              r"driving licen[cs]e|bancomat|carta di credito|credit card|tarjeta de credito)\b")
_DOC_EVENT = (r"(?:pers[oaie]|smarrit\w*|rubat\w*|lost|stolen|perdid\w*|perdi|robad\w*|robaron|perdu\w*|vole\w*|"
              r"scadut\w*|scade\w*|expired?|expiring|vencid\w*|caducad\w*|caduca\w*|perime\w*)")
_GAP = r"(?:\s+(?!" + _CARD_NOUN + r")[^\s]+){0,4}?\s+"
_AND_CARD = r"(?!\s*(?:,|e|ed|and|y|et|con|with|o|or)\s+(?:[^\s]+\s+){0,2}?" + _CARD_NOUN + ")"  # "il bancomat e la carta"
_OTHER_DOC_EVENT = re.compile(r"\b" + _DOC_EVENT + _GAP + _OTHER_DOC + _AND_CARD + r"|\b" + _OTHER_DOC + _GAP
                              + r"(?:(?:e|is|es|esta|est)\s+)?" + _DOC_EVENT)
_PIN = (r"\bpin\b", r"\bpuk\b", r"\bcodici di sicurezza", r"\bcontatti (della|collegati alla) (carta|cie)")
_CARD_LOST = (r"\b(?:pers[oa]|smarrit[oa]|rubat[oa]|lost|stolen|perdid[oa]|robad[oa]|perdu)\b"
              r"(?:\s+(?!pin\b|puk\b|codic)[^\s]+){0,3}?\s+(?:carta|card|cie|carte|tarjeta)\b",
              r"\b(?:carta|card|cie|carte|tarjeta)\b(?:\s+(?!pin\b|puk\b|codic)[^\s]+){0,4}?\s+"
              r"(?:pers[oa]|smarrit|rubat|lost|stolen|perdid|robad)")


def understand(text: str) -> dict:
    """Keyword rules for demo mode: the service, the answers, urgency and the area in a message.

    This is what the demo does instead of Claude: no model, so only explicit words count, and
    anything it can't tell stays a question with buttons. `choices` narrows the service question
    when the words say "residence" but not from where.
    """
    folded = validator.fold(text or "")
    answers: dict[str, str] = {}
    # "permesso in rinnovo" is about the permit, not the card, and so is "ho perso la tessera sanitaria";
    # "in Spagna" says where, not the citizenship
    texts = {"motivo": _OTHER_DOC_EVENT.sub(" ", _PERMIT_RENEWAL.sub(" ", folded)), "cittadinanza": _PLACE.sub(" ", folded)}
    for qid, rules in _ANSWER_WORDS.items():
        for value, pats in rules:
            if pats and _any(pats, texts.get(qid, folded)):
                answers[qid] = value
                break
    if _any(_PIN, folded) and not _any(_CARD_LOST, folded):  # lost PIN/PUK, not a lost card
        answers["motivo"] = "pin-puk"
    hints: dict[str, str] = {}
    if "alloggio" not in answers and _any(_RENT, folded):
        if _any(_NOT_REGISTERED, folded):
            answers["alloggio"] = "affitto"
        elif _any(_REGISTERED, folded):
            answers["alloggio"] = "affitto-registrato"
        else:
            hints["alloggio"] = "affitto"
    if _any(_STUDY, folded) and _any(_WAITING, folded):
        answers["permesso"] = "altro"  # waiting for a first study permit: not one of Annex A's four cases
    elif "permesso" not in answers and _any((r"\bcontratto di soggiorno", r"\bsportello unico"), folded) and _any(
            (r"\bricevuta", r"\breceipt", r"\brecibo", "إيصال", "回执"), folded):
        answers["permesso"] = "ricevuta-lavoro"
    if _any(_CHILD, folded):
        answers["eta"] = "minore"
    elif _any(_FIRST_PERSON, folded):
        answers["eta"] = "adulto"
    rest = folded  # "residente a Padova" names a town, not via Padova in Milan: no office area in it
    for pattern in _OUTSIDE_LOMBARDY:
        rest = _compiled(pattern).sub(" ", rest)
    area = next((name for key, name in _areas()
                 if re.search(r"(?<![a-z])" + re.escape(key) + r"(?![a-z])", rest)), None)
    if "residenza" not in answers and rest != folded:  # resident outside Lombardy: living in Milan or not
        if _any(_NOT_IN_MILAN, folded):
            answers["residenza"] = "altra-regione"
        elif _any(_LIVES_IN_MILAN, folded) or area:
            answers["residenza"] = "domicilio-milano"

    service_id, choices = None, None
    internal = bool(_FROM_PLACE.search(folded)) or _any(_INTERNAL, folded)
    abroad = _any(_ABROAD, folded) or answers.get("cittadinanza") == "extra-ue" or "permesso" in answers
    if _any(_SERVICE_WORDS["carta-identita"], folded):
        service_id = "carta-identita"
    elif internal and not _any(_ABROAD[:4], folded):  # moving from another comune, whatever the citizenship
        service_id = "cambio-residenza"
    elif _any(_SERVICE_WORDS["iscrizione-anagrafica-extra-ue"], folded):
        if answers.get("cittadinanza") == "italiana":
            service_id = "cambio-residenza"  # Italians: another comune, or back from abroad with AIRE
        elif abroad and answers.get("cittadinanza") != "ue":
            service_id = "iscrizione-anagrafica-extra-ue"
        else:  # residence, but from where? (and EU citizens from abroad are not covered yet)
            choices = ["iscrizione-anagrafica-extra-ue", "cambio-residenza"]
    if service_id is None and choices is None and answers.get("motivo") in ("smarrimento-furto", "rinnovo",
                                                                           "deteriorata", "chip", "pin-puk",
                                                                           "gia-cie"):
        service_id = "carta-identita" if _any((r"\bcarta\b", r"\bcard\b", r"\bcarte\b", "证", "بطاقة"), folded) else None
    return {"service_id": service_id, "answers": answers, "urgent": _any(_URGENT, folded), "area": area,
            "hints": hints, "choices": choices}


# ---------- questions in demo mode: the saved official pages' own words, by keyword search ----------
QA_SERVICE = "carta-identita"  # whose pages answer a question when neither the case nor the words name a service
QA_LANGS = (*LANGS, "fr")  # the replay's own lines around the quotes (the quotes stay in the page's language)
QA_MAX_CARDS = 3
QA_MIN_RELATIVE_SCORE = 0.8  # a 2nd or 3rd passage is quoted only when it scores this close to the first (of its part)
EXCERPT_CHARS = 450  # a quote longer than this is cut at a sentence or line end, marked "…"
WHOLE_CHARS = 700  # ... unless the whole passage is this short: then it is quoted whole ("a costo zero" included)
# Who sets a fact: the City's own pages first, the Ministry's next, guides for newcomers (YesMilano) only when
# no City or Ministry card holds what they hold ("ten working days" is not quoted next to the City's six).
PUBLISHER_RANK = {"Comune di Milano": 0, "Ministero dell'Interno": 1}
GUIDE_RANK = 2
# A message that is not worded as a question is still read as one when it is short ("foto in comune",
# "PIN perso") or comes in the middle of a case, and a passage holds most of it.
PROBE_MAX_WORDS = 6
PROBE_CONFIDENCE = 0.8


@functools.lru_cache(maxsize=1)
def qa_script() -> dict:
    """data/demo/qa.json: the replay's lines around the quotes and the example questions."""
    return json.loads((DEMO / "qa.json").read_text(encoding="utf-8"))


def _qa_t(lang: str, key: str, **values: object) -> str:
    templates = qa_script()["templates"]
    return templates.get(lang if lang in QA_LANGS else "en", templates["en"]).get(key, templates["en"][key]).format(**values)


def example_questions(lang: str) -> list[dict]:
    """The example questions the app shows as chips: [{"id", "label", "query"}] in `lang` (else English)."""
    lang = _lang(lang)
    return [{"id": e["id"], "label": e["label"].get(lang) or e["label"]["en"],
             "query": e["query"].get(lang) or e["query"]["en"]} for e in qa_script()["examples"]]


_QUESTION_MARK = re.compile(r"[?？؟¿]")
# Words a question starts with, folded (lower case, no accents, bare Arabic letters). Modal verbs that also
# open statements ("devo", "I need", "necesito") are not here: "Devo fare la residenza" is a case.
_ASK_START = {
    "it": ("quanto", "quanta", "quanti", "quante", "quale", "quali", "qual", "come", "dove", "quando", "cosa",
           "che cosa", "perche", "chi", "posso", "possiamo", "puoi", "si puo", "e possibile", "e vero", "c'e",
           "ci sono", "vale", "occorre",
           "qnt", "qnto", "qnta", "qndo", "qnd", "xke", "xche", "perke", "dv"),  # chat shorthand
    "en": ("how", "what", "which", "where", "when", "why", "who", "can", "could", "do", "does", "did", "is", "are",
           "should", "must", "will", "would", "may", "am i", "have i",
           "wat", "wot", "whats", "wats", "hw", "wht", "wen", "wer", "cn"),
    "es": ("cuanto", "cuanta", "cuantos", "cuantas", "como", "donde", "cuando", "que", "cual", "cuales", "por que",
           "quien", "puedo", "podemos", "se puede", "es posible", "hay que", "tengo que"),
    "fr": ("combien", "comment", "ou", "quand", "quel", "quelle", "quels", "quelles", "pourquoi", "est-ce",
           "puis-je", "peut-on", "dois-je", "faut-il", "est-il"),
    "ar": ("هل", "كم", "كيف", "اين", "متى", "ماذا", "لماذا", "ايش", "شو", "وين", "ليش"),
}
_ASK_RE = {lang: re.compile(r"^(?:(?:ma|e|and|but|so|y|pero|mais|et|ok|allora|scusa|sorry|و)\s*,?\s+)?(?:"
                            + "|".join(re.escape(validator.fold(w)) for w in words) + r")(?![\w'-])")
           for lang, words in _ASK_START.items()}
_ASK_ZH = ("吗", "呢", "什么", "多少", "怎么", "怎样", "如何", "哪里", "哪儿", "哪个", "几", "是否", "能不能",
           "可不可以", "要不要", "需不需要", "有没有", "多久", "多长时间")
_CJK_TEXT = re.compile(r"[㐀-鿿]")
# "How do I start?": a question the case itself answers, not one for the pages.
_GENERIC_START = (
    r"\bda dove (comincio|inizio|parto|cominciamo|iniziamo)\b", r"\bcome (faccio|facciamo|si fa|fare)\b",
    r"\b(cosa|che cosa|che) (devo|dobbiamo|deve) fare\b",
    r"\bcome (prendo|registro|registriamo|chiedo|richiedo|ottengo|rinnovo|rifaccio|procedo|funziona)\b",
    r"\bcosa (devo|dobbiamo) (portare|preparare|presentare)\b", r"\bquali documenti\b", r"\bche documenti\b",
    r"\bmi (puoi |potete )?aiuta",
    r"\bwhere (do|should|can) (i|we) (start|begin)\b",
    r"\bhow (do|can|should) (i|we) (do it|start|begin|get|apply|register|renew|request|proceed)\b",
    r"\bwhat (do|should|must) (i|we) do\b", r"\bwhat now\b",
    r"\bwhat (documents|papers) (do|should) (i|we)\b", r"\bcan you help\b",
    r"\bpor donde (empiezo|empezamos|comienzo)\b", r"\bcomo (lo )?(hago|hacemos)\b",
    r"\bque (tengo|tenemos|debo|debemos) (que )?hacer\b", r"\bque hago\b",
    r"\bcomo (me )?(registro|empadrono|saco|pido|renuevo|tramito)\b", r"\bque documentos\b",
    r"\bpar ou (commencer|je commence)\b", r"\bcomment (faire|je fais|m'inscrire|proceder)\b",
    r"\bque (dois-je|faut-il) faire\b", r"\bquels documents\b",
    "من أين أبدأ", "ماذا أفعل", "ماذا يجب أن أفعل", "كيف أسجل", "كيف أبدأ",
    "怎么办", "从哪里开始", "我该怎么做", "怎么登记", "怎么办理", "如何办理",
)


# Concepts of the search (onevisit/search_synonyms.json) that the case itself answers, with its deciding
# questions and its checklist: a "how do I…" question made only of these is the case ("Come rinnovo la carta
# d'identità?"); one that asks anything else ("¿Cómo pido cita…?", "come faccio a vedere a che punto è la
# lavorazione?") is also a question for the pages.
_CASE_CONCEPTS = frozenset("§" + c for c in (
    "idcard", "documents", "requirements", "mandatory", "lost", "stolen", "police_report", "minor", "parent",
    "adult", "family", "renewal", "expiry", "damaged", "old_card", "paper_card", "foreigner", "citizenship",
    "residence", "residence_permit", "other_comune", "home_service", "pin_puk", "urgent", "travel", "elderly",
    "apply", "change", "single_parent", "guardian", "student", "asylum", "aire", "in_person", "no_document",
    "provisional"))
# Arabic, Chinese… words reach the pages only through the search's concepts: a bare one asks nothing.
_NON_LATIN = re.compile(r"[^\x00-\u024f]")
# A question word inside a message that doesn't start with one ("ho perso il foglio col puk come lo recupero").
_ASK_INSIDE = re.compile(r"(?<![\w'])(?:come|cosa|dove|quando|quanto|quanti|quanta|quante|perche|quale|quali|how|"
                         r"what|where|when|why|which|como|donde|cuando|cuanto|cuanta|cual|comment|combien|"
                         r"pourquoi|quand)(?![\w'])")


def asks_more_than_the_case(text: str) -> bool:
    """A "how do I…" message that asks more than the case answers: once its opening ("come faccio",
    "how do I") is set aside, a search term is left that the case doesn't decide (a concept such as
    booking, tracking, cost or photo, or a Latin-script word of the pages)."""
    rest = validator.fold(text or "")
    for pattern in _GENERIC_START:
        rest = _compiled(pattern).sub(" ", rest)
    return any((t.startswith("§") and t not in _CASE_CONCEPTS and w >= 1.0)
               or (not t.startswith("§") and w >= 1.0 and not t.isdigit() and not _NON_LATIN.search(t))
               for t, w in search.query_terms(rest).items())


# A question word inside a message that is not a question: a comparison ("come mia moglie"), a time
# ("quando ero a Roma"), a place ("dove abito"), a relative clause ("what I need is").
_NOT_ASKING = re.compile(r"(?<![\w'])(?:come (?:il|un|una|uno|mi[ao]|mie|miei|tu[ao]|su[ao]|te|me|lui|lei|"
                         r"noi|voi|loro|sempre|detto|previsto|indicato|da|di|gia|prima|questo|questa)|quando (?:ero|eravamo|"
                         r"sono|siamo|ho|abbiamo|avevo|era|e)|dove (?:abito|vivo|lavoro|sono|sto|abitiamo|viviamo)|"
                         r"what (?:i|we) (?:need|have|did)|when i (?:was|were)|where i (?:live|work|am)|"
                         r"como (?:mi|tu|su|el|la|un|una)|cuando (?:estaba|era|fui))(?![\w'])")


def is_question(text: str) -> bool:
    """True when a message is worded as a question: a question mark (?, ？, ؟, ¿), a question word
    or inverted verb at the start (quanto, posso, how, can, cuánto, combien, هل, كم…, and chat
    shorthand: qnt, xke, wat), a question word inside a short message that doesn't use it to compare
    or to say when or where ("ho perso il foglio col puk come lo recupero", not "come mia moglie"), or
    a Chinese question particle (吗, 什么, 多少…)."""
    text = (text or "").strip()
    if not text:
        return False
    if _QUESTION_MARK.search(text):
        return True
    folded = validator.fold(text).lstrip(" \t\"'“«(-")
    if any(rx.match(folded) for rx in _ASK_RE.values()):
        return True
    inside = [m for m in _ASK_INSIDE.finditer(folded) if not _NOT_ASKING.match(folded, m.start())]
    if inside and len(folded.split()) <= 20:
        return True
    return bool(_CJK_TEXT.search(text)) and any(p in text for p in _ASK_ZH)


def _ask_language(text: str) -> str | None:
    """The language a question's opening word belongs to (Italian, English, Spanish, French, Arabic), else
    by script or the Spanish ¿; None if nothing tells."""
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    if _CJK_TEXT.search(text):
        return "zh"
    if "¿" in text:
        return "es"
    folded = validator.fold(text.strip()).lstrip(" \t\"'“«(-")
    return next((lang for lang, rx in _ASK_RE.items() if rx.match(folded)), None)


def question_language(text: str, fallback: str) -> tuple[str, str | None]:
    """The language the replay answers a question in (its own lines; the quotes stay as published), and the
    language it saw when it can't write it (Ukrainian, Bengali…: answered in English, the language named)."""
    found = guess_lang(text)
    if found and found not in QA_LANGS:  # Ukrainian, Persian, Tagalog…
        return "en", found
    if "¿" in text or "¡" in text:  # Spanish, whatever words it shares with Italian
        return "es", None
    asked = _ask_language(text)  # the question word says more than a short message's other words
    return (asked or found or (fallback if fallback in QA_LANGS else "en")), None


def _new_facts(state: dict, found: dict) -> dict:
    """Answers a message gives to this case's other open deciding questions ("Residente a Milano" typed
    while the replay asks something else). A first-person word alone ("I", "mi") is not an adult's answer."""
    service = kb.get_service(state.get("service_id") or "") or {}
    live = {q["id"]: q for q in _questions(service)}
    out = {}
    for qid, value in (found.get("answers") or {}).items():
        if (qid == "eta" and value == "adulto") or qid not in live or qid in state.get("answers", {}):
            continue
        value = _alias(value, live[qid]["options"])
        if value in live[qid]["options"]:
            out[qid] = value
    return out


_ANAGRAFE_ONLY = re.compile(r"\banagrafe\b")


def _names_residence(text: str) -> bool:
    """The message names residence itself, not only the registry office ("in anagrafe" is where a person
    goes for any procedure, the ID card included)."""
    rest = _ANAGRAFE_ONLY.sub(" ", validator.fold(text or ""))
    return _any(_SERVICE_WORDS["iscrizione-anagrafica-extra-ue"], rest)


def qa_service(state: dict | None, found: dict, text: str | None = None) -> str | None:
    """The service whose pages answer a question: the one the question names, none when it names residence
    without saying which of the two procedures (all pages), else the case's, else the ID card. "In anagrafe"
    alone names the office, not residence."""
    if found.get("service_id"):
        return found["service_id"]
    if found.get("choices") and (text is None or _names_residence(text)):
        return None
    return (state or {}).get("service_id") or QA_SERVICE


def classify(state: dict | None, text: str) -> str:
    """What a message typed in demo mode is, read by rules (no model):

    - "answer": it matches an option of the pending deciding question (a label, its number, or the
      keyword rules: "sono peruviano" answers the citizenship question);
    - "fact": in a case, it answers another open deciding question ("Residente a Milano");
    - "case": it starts a new case: it names a procedure and either says something about the case
      ("ho perso la carta"), is not worded as a question, or only asks how to start ("da dove comincio?");
      a message that names the case already open is not a new case, and a question about another
      procedure while a case is open is a question (the case is kept; the reply offers a new case);
    - "question": it is worded as a question (see is_question), or it is short / comes in the middle of
      a case / has a question word inside, and a saved official page holds most of it ("foto in comune",
      "ho perso il foglio col puk come lo recupero"); a "how do I…" question that names the procedure is a
      question when it says nothing of the case and asks more than the case answers ("¿Cómo pido cita
      para la carta de identidad?");
    - "unclear": none of these (the replay then says what it can read).
    """
    text = (text or "").strip()
    state = state or {}
    if not text:
        return "unclear"
    if state.get("pending") and match_option(state, text):
        return "answer"
    found = understand(text)
    folded = validator.fold(text)
    asking = is_question(text)
    in_case = bool(state.get("service_id")) and not state.get("done")
    if in_case and not asking and _new_facts(state, found):
        return "fact"
    named = bool(found["service_id"] or found.get("choices"))
    says_case = any(k != "eta" for k in found["answers"])
    # "how do I start?" is the case; "¿cómo pido cita para la carta?" asks more (see specific_question)
    generic = _any(_GENERIC_START, folded) and not (asking and not says_case and specific_question(text))
    if asking and state.get("service_id") and named and found["service_id"] != state.get("service_id"):
        return "question"  # about another procedure, a case open: answered, the case kept (ask offers a new case)
    if named and (says_case or not asking or generic) \
            and not (in_case and found["service_id"] == state.get("service_id")):
        return "case"
    if asking:
        return "question"
    if in_case or len(text.split()) <= PROBE_MAX_WORDS or _ASK_INSIDE.search(folded):
        probe = search.best_answer(text, service_id=qa_service(state, found, text), k=1)
        if probe["reason"] == "ok" and probe["confidence"] >= PROBE_CONFIDENCE:
            return "question"
    return "unclear"


_CLAUSES = re.compile(r"(?<=[.!?？؟。！])\s*|[,;:，；：]\s*")


def specific_question(text: str) -> str | None:
    """The question a case-opening message also asks ("Ho perso la carta d'identità, quanto costa
    rifarla?"), unless it only asks how to start, which the case answers ("da dove comincio?", "come
    rinnovo la carta?"); "come faccio a bloccarla?" asks more than the case (asks_more_than_the_case)."""
    for clause in reversed([c.strip() for c in _CLAUSES.split(text or "") if c and c.strip()]):
        if not is_question(clause) or not search.query_terms(clause):
            continue
        if not _any(_GENERIC_START, validator.fold(clause)) or asks_more_than_the_case(clause):
            return clause
    return None


_UPDATED_LINE = re.compile(r"^\s*(?:ultimo aggiornamento|ultima modifica|last updated?)\b", re.IGNORECASE)
_IMAGE_LINE = re.compile(r"^\s*(?:[-*+]\s*)?!\[[^\]]*\]\([^)]*\)\s*$")
# Leftovers of the page's search widget at the end of a passage ("Filtri attivi:", "[Rimuovi tutti i filtri](javascript:…)").
_WIDGET_LINE = re.compile(r"^\s*(?:filtri(?: attivi)?\s*:?|.*\]\(javascript:[^)]*\).*)\s*$", re.IGNORECASE)
_LINK_SPAN = re.compile(r"!?\[[^\]\n]*\]\([^)\n]*\)")
_CUT_AT = re.compile(r"\n|[.;!?](?=\s)|:(?=\s)")


def _plain_line(line: str) -> str:
    return validator.fold(re.sub(r"[#*_`\s]+", " ", line)).strip(" ?.:")


def excerpt(passage: dict, limit: int = EXCERPT_CHARS, query: str | None = None) -> tuple[str, bool]:
    """A verbatim excerpt of a passage, to quote: the passage text without the question heading it
    repeats, the page's "Ultimo aggiornamento" line (the card shows the date), the search widget's
    leftovers at its end ("Filtri attivi") and image-only lines, cut at a sentence or line end near
    `limit` characters (never inside a link). With `query`, a passage too long to quote whole is quoted
    from the lines and sentences that hold most of the question (search.focus), so the answer to
    "can I book for my whole family?" is not left behind "Leggi tutto"; the quote then starts with
    "…". True when it was cut (the quote then ends, or starts, with "…"). Guillemets inside the
    page's text become “ ” (a quote can't hold « »; the validator reads both as the same quote
    mark). Every other character is the page's own, in order, so the validator finds it in the
    passage."""
    lines = (passage.get("text") or "").split("\n")
    heading = (passage.get("heading") or "").split(" > ")[-1]
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and heading and _plain_line(lines[0]) == _plain_line(heading):
        lines.pop(0)
    while lines and (not lines[-1].strip() or _UPDATED_LINE.match(lines[-1]) or _WIDGET_LINE.match(lines[-1])):
        lines.pop()
    body = "\n".join(ln for ln in lines if not _IMAGE_LINE.match(ln)).strip()
    body = re.sub(r"\n\s*\n\s*(?:\n\s*)+", "\n\n", body)
    body = body.replace("«", "“").replace("»", "”")  # a « » quote can't hold « »; the validator reads both as "
    if len(body) <= max(limit, WHOLE_CHARS):  # a short passage is quoted whole: its answer may be at the end
        return body, False
    lead = ""
    if query:
        start = search.focus(query, body, limit)[0]
        start = next((link.start() for link in _LINK_SPAN.finditer(body) if link.start() < start < link.end()), start)
        if start > 0:
            body = body[start:].lstrip()
            lead = "…\n" if _LIST_MARK.match(body) else "… "  # a list item keeps its own line
            if len(body) <= limit:
                return lead + body, True
    cut = None
    for m in _CUT_AT.finditer(body, 0, limit):
        before = re.search(r"(\w+)$", body[:m.start()])
        if m.group() == "." and before and len(before.group(1)) <= 3 and not before.group(1).isdigit():
            continue  # "nr.", "art.", "ecc.": an abbreviation, not the end of a sentence
        if m.group() == "." and body[body.rfind("\n", 0, m.start()) + 1:m.start()].strip().isdigit():
            continue  # "3." opening a line: a list number, not the end of a sentence
        if m.start() >= limit * 0.4:
            cut = m.end() if m.group() != "\n" else m.start()
    if cut is None:
        cut = body.rfind(" ", 0, limit)
        cut = cut if cut > 0 else limit
    for link in _LINK_SPAN.finditer(body):
        if link.start() < cut < link.end():
            cut = link.start()
            break
    return lead + body[:cut].rstrip(" \n,;:-") + " …", True


def _official_link(turn: _Turn, service_ids: list[str], page: dict | None) -> str:
    """The official page(s) to check, as Markdown links with their source ids: the search result's
    official_page, else each service's official page as get_service returns it (so the id is read)."""
    if page and page.get("url"):
        return f"[{page.get('title') or page['url']}]({page['url']}) [{page['source_id']}]"
    out = []
    for sid in service_ids:
        service = turn.call("get_service", {"service_id": sid})
        link = ((service.get("links") or {}).get("official_url") if isinstance(service, dict) else None)
        if link:
            source = kb.get_source(link["source_id"]) or {}
            out.append(f"[{source.get('title') or link['url']}]({link['url']}) [{link['source_id']}]")
    return " · ".join(out)


_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def fragmented(text: str) -> bool:
    """A passage cut from a PDF's layout ("essere riprese con luce / uniforme e senza ombre, / X X / X X…"):
    of six short lines or more (under 40 characters on average: a circular's wrapped prose reads fine), at
    least four and a third are debris: a line of single letters or dashes ("X X", "-"), or a line that goes
    on with the sentence the line before left open (it starts in lower case after a line with no closing
    punctuation). Verbatim, but unreadable as a quote: the replay shows the next passage instead. A list of
    office names or a news item's "Data: / Tematiche:" header is not."""
    lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
    if len(lines) < 6:
        return False
    debris = 0
    for i, line in enumerate(lines):
        if all(len(re.sub(r"\W", "", t)) <= 1 for t in line.split()):
            debris += 1
        elif i and line[0].islower() and not re.search(r"[:;,.!?)]$", lines[i - 1]):
            debris += 1
    short = sum(len(line) for line in lines) / len(lines) < 40  # a circular's wrapped prose reads fine
    return short and debris >= 4 and debris >= len(lines) / 3


def _rank_of(result: dict) -> int:
    return PUBLISHER_RANK.get(result.get("publisher") or "", GUIDE_RANK if result.get("publisher") == "YesMilano" else 1)


def _quote_passages(results: list[dict], reason: str, query: str | None = None) -> list[tuple[dict, str, bool]]:
    """The passages to quote: when the pages answer, the confident ones (other pages first, at most
    QA_MAX_CARDS; after the first of each part of the question, only those scoring QA_MIN_RELATIVE_SCORE of
    that part's best: "how much, and how many photos?" gets a card for each); when the match is weak, the two
    closest; else none. A Ministry passage or a guide for newcomers (YesMilano) is left out when a City card
    already shown holds the question's concepts it holds, and a Ministry one too when the question asks what
    the City sets (its fee, offices, hours, booking): the City's page says what holds in Milan."""
    if reason == "ok":
        pool = [r for r in results if r.get("confident")] or results[:1]
        limit = QA_MAX_CARDS
    elif reason == "weak_match":  # the closest, leaving out a section about another thing (the PIN codes)
        pool = [r for r in results if not search.heading_mismatch(r.get("part") or query or "", r["passage_id"])][:2]
        limit = 2
    else:
        return []
    best: dict = {}
    for r in pool:
        best.setdefault(r.get("part"), r.get("score") or 0)
    # other pages before a page's second passage, guides for newcomers after the City's and the Ministry's pages
    ordered = sorted(enumerate(pool), key=lambda x: (x[1]["source_id"] in {p["source_id"] for p in pool[:x[0]]},
                                                     _rank_of(x[1]) == GUIDE_RANK, x[0]))
    local = bool(query) and bool(set(search.query_terms(query)) & search.LOCAL_CONCEPTS)
    held: dict[str, frozenset[str]] = {}

    def holds(r: dict) -> frozenset[str]:
        if r["passage_id"] not in held:
            held[r["passage_id"]] = search.held_concepts(r.get("part") or query or "", r["passage_id"])
        return held[r["passage_id"]]

    out: list[tuple[dict, str, bool]] = []
    for _, r in ordered:
        if reason == "ok" and out and (r.get("score") or 0) < QA_MIN_RELATIVE_SCORE * best.get(r.get("part"), 0):
            continue
        rank = _rank_of(r)
        if out and rank > 0 and query and any(
                _rank_of(c) == 0 and holds(c) >= holds(r) for c, _, _ in out) and (rank == GUIDE_RANK or local):
            continue  # the City's card already says it
        text, cut = excerpt(r, query=r.get("part") or query)
        if len(text) >= 40 and not fragmented(text) and not any(text == q for _, q, _ in out):
            out.append((r, text, cut))
        if len(out) >= limit:
            break
    return out


def _qa_paragraphs(turn: _Turn, query: str, lang: str, service_id: str | None, found: dict,
                   short: bool = False) -> tuple[list[str], dict]:
    """Search the saved official pages for `query` and write the answer: a lead, the passages quoted
    verbatim («…» [source_id]) and the line that sends to the official page; when the pages don't answer
    with certainty, that line first (and the closest passages, for a weak match). `short`: for a question
    asked inside a case-opening message or with an answer: the lead and the quotes, or the line saying the
    pages don't answer it (with the closest passage for a weak match), never nothing."""
    args = {"query": query, **({"service_id": service_id} if service_id else {})}
    out = turn.call("search_official_pages", args)
    out = out if isinstance(out, dict) else {}
    results = [r for r in out.get("results") or [] if isinstance(r, dict) and r.get("text")]
    reason = out.get("reason") or ("ok" if results else "no_match")
    quoted = _quote_passages(results, reason, query)
    if reason == "ok" and not quoted:
        reason = "weak_match"
    services = [service_id] if service_id else (found.get("choices") or [QA_SERVICE])
    info = {"query": query, "reason": reason, "service_id": service_id, "found": len(results),
            "pages": len({r["source_id"] for r in results}),
            "cards": [{"source_id": r["source_id"], "passage_id": r.get("passage_id"), "text": q, "cut": cut,
                       "title": r.get("title"), "publisher": r.get("publisher"), "url": r.get("url"),
                       "updated_at": r.get("updated_at"), "saved_at": r.get("saved_at")} for r, q, cut in quoted]}
    quotes = [f"«{q}» [{r['source_id']}]" for r, q, _ in quoted]
    if reason == "ok":
        lead = "also" if short else ("lead_one" if len(quotes) == 1 else "lead")
        paragraphs = [_qa_t(lang, lead), *quotes]
        if not short:
            link = _official_link(turn, services, out.get("official_page"))
            paragraphs.append(_qa_t(lang, "check", link=link) if link else "")
        return paragraphs, info
    if short:  # a question inside a case opening: say the pages don't answer it, with the closest FAQ if weak
        link = _official_link(turn, services, out.get("official_page"))
        paragraphs = [_qa_t(lang, "also_honest", link=link) if link else _qa_t(lang, "honest_nolink", url=OFFICIAL_HOME)]
        if reason == "weak_match" and quotes:
            paragraphs += [_qa_t(lang, "also_closest"), quotes[0]]
            info["cards"] = info["cards"][:1]
        else:
            info["cards"] = []
        return paragraphs, info
    paragraphs = []
    if reason == "other_document" and service_id:
        paragraphs.append(_qa_t(lang, "other_document", service=service_title(kb.get_service(service_id) or {}, lang)))
    elif reason == "off_topic":  # the weather, small talk: no passage is quoted, not even the closest
        paragraphs.append(_qa_t(lang, "off_topic"))
    link = _official_link(turn, services, out.get("official_page"))
    paragraphs.append(_qa_t(lang, "honest", link=link) if link else _qa_t(lang, "honest_nolink", url=OFFICIAL_HOME))
    if quotes:
        paragraphs += [_qa_t(lang, "closest"), *quotes]
    else:
        info["cards"] = []
    return paragraphs, info


def _back_to_case(state: dict, lang: str) -> tuple[list[str], list[tuple[str, str]] | None]:
    """After a question in the middle of a case: the pending question again, with its options."""
    pending = state.get("pending")
    if pending == SERVICE_CHOICE:
        return [_qa_t(lang, "back_choice")], _service_options(state["lang"], state.get("choices"))
    if not pending:
        return [], []
    service = kb.get_service(state["service_id"]) or {}
    question = next((q for q in _questions(service) if q["id"] == pending), None)
    if not question:
        return [], []
    text = question_text(service["id"], question, lang, narrowed(question, state.get("hints")))
    return [_qa_t(lang, "back", question=text)], None


# "Where is the nearest office?", "c'è la cabina foto a Isola?": the offices come from the open dataset (ds549).
_NEAREST = (r"\bpiu vicin", r"\bnearest\b", r"\bclosest\b", r"\bnear me\b", r"\bmas cercan", r"\bcerca de mi\b",
            r"\ble plus proche\b", r"\bpres de chez moi\b", "最近的", "离我最近", "الأقرب", "أقرب مكتب")


def _office_paragraphs(turn: _Turn, text: str, lang: str, found: dict) -> tuple[list[str], str | None]:
    """The offices a question names by neighbourhood or street ("a Isola": the office there, from the open
    dataset, find_offices), or the official list of offices when it asks for the nearest one and names no
    area the data knows; and the office's street, to search the pages with ("De Benedetti": the photo
    booths page names the offices by street). ([], None) when the question asks nothing about an office."""
    folded = validator.fold(text)
    area = found.get("area")
    nearest = _any(_NEAREST, folded)
    if not area and not nearest:
        return [], None
    if area:
        offices = turn.call("find_offices", {"area": area, "limit": 1})
        if isinstance(offices, list) and offices:
            office = offices[0]
            cites = _cites([office.get("source_id", "ds549")] + ([office["entrance_confirmed_by"]["source_id"]]
                                                                 if office.get("entrance_confirmed_by") else []))
            street = re.sub(r"^(?:via|viale|piazza|piazzale|largo)\s+|\s+\d+.*$", "", office["address"], flags=re.IGNORECASE)
            return [_qa_t(lang, "office_area", area=area, office=office_where(office), cite=cites)], street
    if nearest:
        page = turn.call("get_source", {"source_id": "sedi-anagrafiche"})
        if isinstance(page, dict) and page.get("url"):
            link = f"[{page.get('title') or page['url']}]({page['url']}) [sedi-anagrafiche]"
            return [_qa_t(lang, "office_list", link=link)], None
    return [], None


def _pending_options(state: dict) -> list[tuple[str, str]]:
    """The options of the pending deciding question (or of the service choice), as _finish shows them."""
    if state.get("pending") == SERVICE_CHOICE:
        return _service_options(state["lang"], state.get("choices"))
    q = state.get("pending")
    service = (kb.get_service(state["service_id"]) if state.get("service_id") else None) or {}
    question = next((x for x in _questions(service) if x["id"] == q), None) if q else None
    narrow = narrowed(question, state.get("hints")) if question else None
    return [(o, option_label(o, state["lang"])) for o in (narrow or question or {}).get("options") or []]


NEW_CASE = "__new_case__"


def ask(state: dict, text: str, lang: str | None = None) -> dict:
    """Answer a question in demo mode from the saved official pages, extractively: no model, the passages
    the keyword search ranks first, quoted verbatim with their page, publisher and date (reply["qa"]),
    and an honest line with the official page when the pages don't answer with certainty. The case in
    `state` (answers, pending question) is kept: the reply asks the pending question again, with its
    options; a question about another procedure keeps the case open and offers a button that opens the
    other one (state["new_case_offer"]). A neighbourhood or street names an office (the open dataset), and
    "the nearest office" gets the official list. The reply's own lines follow the question's language
    (Italian, English, Arabic, Spanish, Chinese, French); the quotes stay in the page's language."""
    found = understand(text)
    qlang, other = question_language(text, lang or state.get("lang") or "it")
    if qlang in LANGS:
        state["lang"] = qlang
    turn = _Turn()
    query = text.strip()[:search.MAX_QUERY_CHARS]
    offices, street = _office_paragraphs(turn, query, qlang, found)
    service_id = qa_service(state, found, query)
    if offices and not street:  # "the nearest office": the list of offices answers, not a passage
        paragraphs, info = offices, {"query": query, "reason": "offices", "service_id": service_id, "found": 0,
                                     "pages": 0, "cards": []}
    else:
        paragraphs, info = _qa_paragraphs(turn, f"{query} {street}" if street else query, qlang, service_id, found)
        paragraphs = offices + paragraphs
    note = [_t("en", "other_language", language=LANGUAGE_NAMES.get(other, other))] if other else []
    back, options = _back_to_case(state, qlang)
    # a question about another procedure while a case is open: the case stays, a button opens the other one
    other_service = found.get("service_id") if state.get("service_id") and found.get("service_id") != state["service_id"] else None
    state["new_case_offer"] = None
    if other_service:
        current = service_title(kb.get_service(state["service_id"]) or {}, qlang)
        label = _qa_t(qlang, "new_case_label", service=service_title(kb.get_service(other_service) or {}, qlang))
        state["new_case_offer"] = {"service_id": other_service, "label": label, "found": found}
        back = [_qa_t(qlang, "kept_case", service=current), *back]
        options = [*(options if options is not None else _pending_options(state)), (NEW_CASE, label)]
    reply = _finish(state, turn, note + paragraphs + back, options=options, quotes=True)
    reply.update({"qa": info, "routing": "search", "lang": qlang, "other_language": other})
    return reply


def respond(state: dict | None, text: str, lang: str) -> tuple[dict, dict]:
    """One message typed in demo mode, whatever it is (see classify): the next turn of the case in
    progress, a new case, or a question answered from the saved official pages. Returns the state to
    keep (the same dict while a case is in progress) and the reply."""
    if state and (state.get("service_id") or state.get("pending")):
        reply = answer(state, text)
        return state, reply
    return start_text(text, lang)


def _service_options(lang: str, only: list[str] | None = None) -> list[tuple[str, str]]:
    ids = [s["id"] for s in kb.list_services()]
    ids = [i for i in (only or ids) if i in ids]
    return [(sid, service_title(kb.get_service(sid) or {"id": sid}, lang)) for sid in ids]


def _question_query(text: str, clause: str) -> str:
    """What to search for a question asked inside a longer message: the whole message (cut to the
    search's limit), so that what comes before the question stays in it ("Mi pasaporte está vencido,
    ¿puedo sacar la carta?" is about the passport too); the question's own clause when the message is
    mostly the case (several sentences before it)."""
    before = text[: text.rfind(clause)] if clause in text else ""
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", before) if x.strip()]
    return (clause if len(sentences) >= 2 else text.strip())[: search.MAX_QUERY_CHARS]


def start_text(text: str, lang: str, lead: list[str] | None = None) -> tuple[dict, dict]:
    """First turn from a typed message in demo mode (keyword rules, then live tools).

    The reply follows the message's language when the replay writes it; otherwise it is in English
    and opens by naming the language it saw (the live version, with Claude, answers in it).
    A question (see classify) is answered from the saved official pages, with no case opened; a case
    opening that also asks something specific ("…, quanto costa rifarla?") gets the passages first, or
    the line saying the pages don't answer it. `lead`: lines to say first (the earlier case was closed)."""
    if classify(None, text) == "question":
        state = new_state(None, reply_language(text, lang)[0], persona=None, routing="keywords")
        return state, ask(state, text, lang)
    lang, other = reply_language(text, lang)
    found = understand(text)
    state = new_state(found["service_id"], lang, persona=None, urgent=found["urgent"], routing="keywords",
                      typed=found, hints=dict(found.get("hints") or {}), other_language=other)
    note = [_t(lang, "other_language", language=LANGUAGE_NAMES.get(other, other))] if other else []
    note += lead or []
    turn = _Turn()
    if not found["service_id"]:
        turn.call("list_services", {})
        state["pending"] = SERVICE_CHOICE
        state["choices"] = found.get("choices")
        key = "which_residence" if found.get("choices") else "which_service"
        return state, _finish(state, turn, note + [_t(lang, key)], options=_service_options(lang, found.get("choices")))
    area = found["area"] if found["service_id"] == "carta-identita" else None
    paragraphs = _begin(state, turn, found["answers"], area, area)
    asked = specific_question(text)
    if asked and not any("«" in p for p in paragraphs):  # the quote check reads every « » of the reply
        qa, info = _qa_paragraphs(turn, _question_query(text, asked), lang, state["service_id"], found, short=True)
        if qa:
            reply = _finish(state, turn, note + qa + paragraphs, quotes=True)
            reply["qa"] = info
            return state, reply
    return state, _finish(state, turn, note + paragraphs)


def start_appointment(service_id: str, office_id: str | None, date: str | None, lang: str) -> tuple[dict, dict]:
    """First turn when the citizen arrives from the booking confirmation link."""
    lang = _lang(lang)
    state = new_state(service_id, lang, date=date, persona=None)
    turn = _Turn()
    service = turn.call("get_service", {"service_id": service_id})
    if not isinstance(service, dict) or "error" in service:
        return state, _finish(state, turn, [_t(lang, "start_free")])
    checklist = turn.call("get_checklist", {"service_id": service_id, "answers": {}})
    state["checklist"] = checklist
    office = None
    if office_id:
        match = next((o for o in kb.find_offices(limit=1000) if o["id"] == office_id), None)
        if match:
            found = turn.call("find_offices", {"area": match["address"], "limit": 1})
            office = found[0] if isinstance(found, list) and found else None
    if office:
        state["offices"] = [office]
        state["office_id"] = office["id"]
        cites = [office.get("source_id", "ds549")] + ([office["entrance_confirmed_by"]["source_id"]]
                                                      if office.get("entrance_confirmed_by") else [])
        paragraphs = [_t(lang, "deeplink", service=service_title(service, lang), date=format_date(date) or "—",
                         office=office_where(office), office_cite=_cites(cites))]
    else:
        paragraphs = [_t(lang, "opening", service=service_title(service, lang))]
    paragraphs += _ask_or_finish(state, turn, service, checklist, first=True)
    return state, _finish(state, turn, paragraphs)


def idle(lang: str) -> dict:
    """Reply to an empty or unclear start (no tools, nothing stated)."""
    state = new_state(None, lang)
    return _finish(state, _Turn(), [_t(lang, "start_free")], options=[])


def match_option(state: dict, text: str) -> str | None:
    """Map what the citizen clicked or typed to an option id of the pending question."""
    if not state.get("pending"):
        return None
    needle = validator.fold(text.strip())
    if state["pending"] == SERVICE_CHOICE:
        only = state.get("choices")
        for sid, label in _service_options(state["lang"], only) + _service_options("it", only) + _service_options("en", only):
            if needle in (validator.fold(label), validator.fold(sid)):
                return sid
        return None
    service = kb.get_service(state["service_id"]) or {}
    question = next((q for q in _questions(service) if q["id"] == state["pending"]), None)
    if not question:
        return None
    shown = (narrowed(question, state.get("hints")) or question)["options"]
    for i, opt in enumerate(shown, start=1):
        labels = {validator.fold(opt), validator.fold(humanize(opt)), str(i)}
        labels |= {validator.fold(v) for v in script()["options"].get(opt, {}).values()}
        if needle in labels:
            return opt
    found = understand(text).get("answers", {}).get(question["id"])  # e.g. "not registered yet" -> affitto
    found = _alias(found, question["options"]) if found else None
    return found if found in question["options"] else None


def _closed_line(state: dict, lang: str) -> list[str]:
    """"I closed the earlier case (…)": said when a new case replaces one in progress."""
    if not state.get("service_id"):
        return []
    return [_qa_t(lang, "closed_case", service=service_title(kb.get_service(state["service_id"]) or {}, lang))]


def _new_case(state: dict, text: str) -> dict:
    """A new case typed after (or in the middle of) another one: the state starts again, and the reply
    says that the earlier case was closed."""
    lang = reply_language(text, state["lang"])[0]
    fresh, reply = start_text(text, state["lang"], lead=_closed_line(state, lang))
    state.clear()
    state.update(fresh)
    return reply


def _open_offered(state: dict, offer: dict) -> dict:
    """The "new case" button of a reply to a question about another procedure: that case opens with what
    the question said ("se l'ho persa": lost), and the reply says the earlier one was closed."""
    lang = state["lang"]
    found = offer.get("found") or understand("")
    fresh = new_state(offer["service_id"], lang, persona=None, urgent=bool(found.get("urgent")), routing="keywords",
                      typed=found, hints=dict(found.get("hints") or {}))
    turn = _Turn()
    area = found.get("area") if offer["service_id"] == "carta-identita" else None
    paragraphs = _closed_line(state, lang) + _begin(fresh, turn, found.get("answers") or {}, area, area)
    reply = _finish(fresh, turn, paragraphs)
    state.clear()
    state.update(fresh)
    return reply


def answer(state: dict, text: str) -> dict:
    """Next scripted turn: the citizen picked an option or typed something (see classify): an answer,
    an answer to another open question, a new case, or a question answered from the official pages
    (the case is kept and its pending question asked again)."""
    lang = state["lang"]
    turn = _Turn()
    offer = state.pop("new_case_offer", None)
    if offer and text.strip() == offer.get("label"):  # the "new case" button
        return _open_offered(state, offer)
    kind = classify(state, text)
    if kind == "question":
        return ask(state, text)
    if state.get("pending") == SERVICE_CHOICE:
        service_id = match_option(state, text)
        if not service_id and kind == "case":
            return _new_case(state, text)
        if not service_id:
            only = state.get("choices")
            return _finish(state, turn, [_t(lang, "which_residence" if only else "which_service")],
                           options=_service_options(lang, only))
        typed = state.get("typed") or {}
        state.update(new_state(service_id, lang, persona=None, urgent=bool(typed.get("urgent")), routing="keywords",
                               typed=typed, hints=dict(typed.get("hints") or {})))
        area = typed.get("area") if service_id == "carta-identita" else None
        return _finish(state, turn, _begin(state, turn, typed.get("answers") or {}, area, area))
    if kind == "case":
        return _new_case(state, text)
    if kind == "fact":  # e.g. "Residente a Milano" while another question is pending: noted, then on
        facts = _new_facts(state, understand(text))
        state["answers"].update(facts)
        service = turn.call("get_service", {"service_id": state["service_id"]})
        checklist = turn.call("get_checklist", {"service_id": state["service_id"], "answers": dict(state["answers"])})
        state["checklist"] = checklist
        noted = [_t(lang, "understood", facts=", ".join(option_label(v, lang) for v in facts.values()))]
        paragraphs = noted + _urgent_once(state, checklist) + _ask_or_finish(state, turn, service, checklist, first=False)
        return _finish(state, turn, paragraphs)
    option = match_option(state, text)
    if option is None:
        return _finish(state, turn, [_t(lang, "done" if state.get("done") else "free_text")])
    state["answers"][state["pending"]] = option
    # an answer may say more ("Residente a Milano, ho perso la carta") and ask something ("…, e quanto costa?")
    found = understand(text)
    state["answers"].update(_new_facts(state, found))
    service = turn.call("get_service", {"service_id": state["service_id"]})
    checklist = turn.call("get_checklist", {"service_id": state["service_id"], "answers": dict(state["answers"])})
    state["checklist"] = checklist
    paragraphs = _urgent_once(state, checklist) + _ask_or_finish(state, turn, service, checklist, first=False)
    asked = specific_question(text)
    if asked and not any("«" in p for p in paragraphs):
        qa, info = _qa_paragraphs(turn, asked, lang, state["service_id"], found, short=True)
        reply = _finish(state, turn, qa + paragraphs, quotes=True)
        reply["qa"] = info
        return reply
    return _finish(state, turn, paragraphs)


def play(persona_id: str, lang: str, max_turns: int = 8) -> tuple[dict, list[dict]]:
    """Play a persona to the end with its scripted answers (used by tests and the pitch)."""
    persona = personas()[persona_id]
    state, user_text, reply = start_persona(persona_id, lang)
    turns = [{"user": user_text, **reply}]
    for _ in range(max_turns):
        if state.get("done") or not state.get("pending"):
            break
        service = kb.get_service(state["service_id"]) or {}
        question = next(q for q in _questions(service) if q["id"] == state["pending"])
        shown = (narrowed(question, state.get("hints")) or question)["options"]
        choice = persona["answers"].get(question["id"])
        if choice not in shown:
            choice = shown[0]
        label = option_label(choice, lang)
        turns.append({"user": label, **answer(state, label)})
    return state, turns


def draft(group: dict) -> str | None:
    """The recorded staff-panel correction for a report group, if there is one."""
    data = json.loads((DEMO / "drafts.json").read_text(encoding="utf-8"))
    return data.get("drafts", {}).get(f"{group['service_id']}|{group['cause']}")
