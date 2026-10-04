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
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import pathlib
import re

from onevisit import kb, validator
from onevisit.agent import guess_lang
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


def _finish(state: dict, turn: _Turn, paragraphs: list[str], options: list[tuple[str, str]] | None = None) -> dict:
    """Validate the scripted text like a live answer and build the reply."""
    text = "\n\n".join(p for p in paragraphs if p)
    known = set(kb.sources())
    read = set(state.get("read", [])) | validator.sources_in_trace(turn.trace)
    state["read"] = sorted(read)
    reasons = validator.check_reply(text, known_ids=known, read_ids=read,
                                    used_facts=validator.used_facts(turn.trace, text))
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
    out = []
    for q in service.get("deciding_questions", []):
        route = (q.get("option_routes") or {}).get(answers.get(q["id"]))
        if route:
            out.append(route)
    return out


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
        ("domicilio-milano", (r"\bdomicili\w* a milano", r"\bresiden\w* fuori (dalla )?(lombardia|regione)",
                              r"\bresident outside lombardy",
                              r"\bresiden\w*\s+(a|in|en|à)\s+(torino|turin|roma|rome|napoli|naples|bologna|firenze|"
                              r"florence|"
                              r"genova|genoa|venezia|venice|verona|padova|padua|trieste|trento|bolzano|parma|modena|"
                              r"palermo|catania|bari|cagliari|perugia|ancona|pescara|aosta)\b")),
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
    # "permesso in rinnovo" is about the permit, not the card; "in Spagna" says where, not the citizenship
    texts = {"motivo": _PERMIT_RENEWAL.sub(" ", folded), "cittadinanza": _PLACE.sub(" ", folded)}
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
    area = next((name for key, name in _areas()
                 if re.search(r"(?<![a-z])" + re.escape(key) + r"(?![a-z])", folded)), None)

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


def _service_options(lang: str, only: list[str] | None = None) -> list[tuple[str, str]]:
    ids = [s["id"] for s in kb.list_services()]
    ids = [i for i in (only or ids) if i in ids]
    return [(sid, service_title(kb.get_service(sid) or {"id": sid}, lang)) for sid in ids]


def start_text(text: str, lang: str) -> tuple[dict, dict]:
    """First turn from a typed message in demo mode (keyword rules, then live tools).

    The reply follows the message's language when the replay writes it; otherwise it is in English
    and opens by naming the language it saw (the live version, with Claude, answers in it)."""
    lang, other = reply_language(text, lang)
    found = understand(text)
    state = new_state(found["service_id"], lang, persona=None, urgent=found["urgent"], routing="keywords",
                      typed=found, hints=dict(found.get("hints") or {}), other_language=other)
    note = [_t(lang, "other_language", language=LANGUAGE_NAMES.get(other, other))] if other else []
    turn = _Turn()
    if not found["service_id"]:
        turn.call("list_services", {})
        state["pending"] = SERVICE_CHOICE
        state["choices"] = found.get("choices")
        key = "which_residence" if found.get("choices") else "which_service"
        return state, _finish(state, turn, note + [_t(lang, key)], options=_service_options(lang, found.get("choices")))
    area = found["area"] if found["service_id"] == "carta-identita" else None
    paragraphs = _begin(state, turn, found["answers"], area, area)
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


def answer(state: dict, text: str) -> dict:
    """Next scripted turn: the citizen picked an option (or typed something)."""
    lang = state["lang"]
    turn = _Turn()
    if state.get("pending") == SERVICE_CHOICE:
        service_id = match_option(state, text)
        if not service_id:
            only = state.get("choices")
            return _finish(state, turn, [_t(lang, "which_residence" if only else "which_service")],
                           options=_service_options(lang, only))
        typed = state.get("typed") or {}
        state.update(new_state(service_id, lang, persona=None, urgent=bool(typed.get("urgent")), routing="keywords",
                               typed=typed, hints=dict(typed.get("hints") or {})))
        area = typed.get("area") if service_id == "carta-identita" else None
        return _finish(state, turn, _begin(state, turn, typed.get("answers") or {}, area, area))
    option = match_option(state, text)
    if option is None:
        found = understand(text)
        if (found["service_id"] or found.get("choices")) and (state.get("done") or found["service_id"] != state.get("service_id")):
            fresh, reply = start_text(text, lang)  # a new case typed after the first one
            state.clear()
            state.update(fresh)
            return reply
        return _finish(state, turn, [_t(lang, "done" if state.get("done") else "free_text")])
    state["answers"][state["pending"]] = option
    service = turn.call("get_service", {"service_id": state["service_id"]})
    checklist = turn.call("get_checklist", {"service_id": state["service_id"], "answers": dict(state["answers"])})
    state["checklist"] = checklist
    paragraphs = _urgent_once(state, checklist) + _ask_or_finish(state, turn, service, checklist, first=False)
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
