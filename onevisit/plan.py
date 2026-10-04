"""Your next 3 actions: Claude puts the verified checklist in order for this person.

Claude reads the checklist items that apply to the case (from onevisit/kb.py, each with its
source) and the path across offices, and returns, as a structured output, the three things
to do next: which item ids each action covers, one short sentence in the citizen's language,
and why it comes at that point. Code then checks every action before the citizen sees it:

- every requirement id must be an item of this checklist (Claude can't add a requirement);
- the sentences must not claim eligibility or validity (onevisit/validator.py);
- the sources shown are the ones of the cited items, never words Claude wrote.

An action that fails a check is dropped and counted. Without a key the app shows
`fallback_actions`: the first items not yet ticked, in the order of the City's own pages,
labelled as ordered without Claude.

    from onevisit import plan
    result = plan.claude_actions("iscrizione-anagrafica-extra-ue", answers, "ar", ticked=set(), client=client)
    result["actions"], result["rejected"]
"""
from __future__ import annotations

import json

from onevisit import kb, validator
from onevisit.agent import FALLBACK, MODEL

LANG_NAMES = {"it": "Italian", "en": "English", "ar": "Arabic", "es": "Spanish", "zh": "Simplified Chinese",
              "fr": "French", "pt": "Portuguese"}

SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "requirement_ids": {"type": "array", "items": {"type": "string"}},
                    "action": {"type": "string", "description": "One short imperative sentence, in the citizen's language"},
                    "why": {"type": "string", "description": "Why now: the dependency or deadline, in the citizen's language"},
                },
                "required": ["requirement_ids", "action", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["actions"],
    "additionalProperties": False,
}

PROMPT = """You help a newcomer prepare a City of Milan registry procedure: {service}.
Their answers: {answers}.{appointment}
Below are the only facts you may use: the verified checklist items for this case (each with its id, category and official source) and the path across offices.

Pick the 3 actions this person should do next, in order. Prefer what blocks later steps (documents another office must issue first, papers to collect before the application or the appointment) over things that only happen afterwards. Skip items in the "after" category unless nothing else is left.
For each action:
- requirement_ids: 1 to 3 ids from the list below that the action covers;
- action: one short imperative sentence in {language} that only restates those items: no new documents, numbers, offices or deadlines;
- why: one short sentence in {language} on why it comes now, using only the path and the items below.
Never say or imply that the person or their documents are eligible, valid, complete, accepted or guaranteed: the City's officers decide.

Checklist items (JSON):
{items}

Path across offices (JSON):
{steps}"""


def _items(service_id: str, answers: dict, lang: str, ticked: set[str]) -> list[dict]:
    cl = kb.checklist(service_id, answers)
    out = []
    for r in cl["requirements"]:
        if r["id"] in ticked:
            continue
        text, _ = kb.req_text(service_id, r, lang)
        out.append({"id": r["id"], "category": r.get("category"), "text": text, "text_it": r["text_it"],
                    "source_id": r["source_id"]})
    return out


def check_actions(raw: list[dict], items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep the actions whose ids are checklist items and whose words make no promise."""
    by_id = {i["id"]: i for i in items}
    kept, rejected = [], []
    for a in raw:
        ids = [i for i in dict.fromkeys(a.get("requirement_ids") or [])]
        words = f"{a.get('action', '')} {a.get('why', '')}"
        reasons = []
        if not ids:
            reasons.append("no_requirement")
        reasons += [f"unknown_requirement:{i}" for i in ids if i not in by_id]
        reasons += [f"eligibility_claim:{p}" for p in validator.forbidden_phrases_in(words)]
        if validator.cited_source_ids(words):
            reasons.append("source_in_text")  # sources come from the items, not from Claude's words
        if reasons:
            rejected.append({"reasons": reasons})
            continue
        kept.append({"requirement_ids": ids, "action": a["action"].strip(), "why": (a.get("why") or "").strip(),
                     "source_ids": list(dict.fromkeys(by_id[i]["source_id"] for i in ids))})
    return kept[:3], rejected


def claude_actions(service_id: str, answers: dict, lang: str, *, ticked: set[str] | None = None, client,
                   appointment: str | None = None) -> dict:
    """Claude ranks the next 3 actions from the verified items; code checks each one."""
    service = kb.get_service(service_id) or {}
    items = _items(service_id, answers, lang, ticked or set())
    if not items:
        return {"actions": [], "rejected": [], "by": "claude", "model": MODEL}
    steps = [{"order": s.get("order"), "who": s.get("ente"), "text": s.get("text_en") or s.get("text_it"),
              "routes": [r.get("text_en") or r.get("text_it") for r in s.get("routes") or []]}
             for s in service.get("steps", [])]
    prompt = PROMPT.format(
        service=(service.get("title") or {}).get("en", service_id),
        answers=json.dumps(answers, ensure_ascii=False),
        appointment=f" They already have an appointment on {appointment}: don't tell them to book." if appointment else "",
        language=LANG_NAMES.get(lang, "English"),
        items=json.dumps([{k: i[k] for k in ("id", "category", "text", "source_id")} for i in items], ensure_ascii=False),
        steps=json.dumps(steps, ensure_ascii=False),
    )
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=4000, messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}, **FALLBACK,
    )
    if resp.stop_reason == "refusal":
        return {"actions": [], "rejected": [{"reasons": ["refused"]}], "by": "claude", "model": MODEL}
    data = json.loads("".join(b.text for b in resp.content if b.type == "text") or "{}")
    kept, rejected = check_actions(data.get("actions") or [], items)
    return {"actions": kept, "rejected": rejected, "by": "claude", "model": MODEL}


def fallback_actions(service_id: str, answers: dict, lang: str, *, ticked: set[str] | None = None) -> dict:
    """Without Claude: the first three items still to prepare, in the order of the City's pages."""
    cl = kb.checklist(service_id, answers)
    todo = [r for r in kb.to_upload(cl) if r["id"] not in (ticked or set())]
    if len(todo) < 3:
        todo += [r for r in cl["requirements"] if (r.get("category") or "prepare") == "prepare"
                 and r["id"] not in (ticked or set()) and r not in todo]
    actions = []
    for r in todo[:3]:
        text, _ = kb.req_text(service_id, r, lang)
        actions.append({"requirement_ids": [r["id"]], "action": text, "why": "", "source_ids": [r["source_id"]]})
    return {"actions": actions, "rejected": [], "by": "data"}
