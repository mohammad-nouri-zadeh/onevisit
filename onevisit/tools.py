"""Tool definitions for the Claude API, backed by onevisit/kb.py and onevisit/search.py.

The agent team plugs these into their loop:

    from onevisit.tools import TOOLS, run_tool
    response = client.messages.create(..., tools=TOOLS, ...)
    # for each tool_use block:  run_tool(block.name, block.input)  -> string for the tool_result
    # the agent passes the conversation's service, the default for search_official_pages:
    run_tool(block.name, block.input, service_id="carta-identita")

Two tools answer open questions from the saved official pages (data/pages/*.md):

- search_official_pages {query, service_id?} -> onevisit.search.run_tool's JSON: "results"
  (passages: source_id, passage_id, title, publisher, url, saved_at, updated_at, kind, lang,
  heading, text verbatim, score, confidence, confident), "confident", "reason", a "note" when
  nothing (or little) matches, and "official_page" {url, source_id, title} when the service
  is known. Without service_id in the input, the conversation's service is used.
- read_source {source_id} -> {source_id, title, publisher, url, updated_at, saved_at,
  passages: [{passage_id, heading, text}], truncated}: the whole saved page, verbatim, in
  page order, capped to READ_SOURCE_MAX_CHARS characters.

Same shape as the hackathon starter (starter/runs_on_claude.py).
"""
import json

from onevisit import kb, search

# read_source returns at most this many characters of passage text (~3k tokens).
READ_SOURCE_MAX_CHARS = 12_000

TOOLS = [
    {
        "name": "list_services",
        "description": "List the City services OneVisit covers and how many of their requirements are verified against an official source.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_service",
        "description": "Get one service: the questions whose answers change what the citizen needs, the steps across offices (a step may list alternative routes, e.g. who assigns the tax code, each with its source_id), the official links (page, booking page, online application form) each with its source_id, where the online application is sent (online_form_kind: 'city' for the City's own form, 'anpr' for the national registry website), whether get_form_guide applies, and what the sources don't cover yet. A deciding question may have a 'narrow' form to ask instead when the message already gives a hint (e.g. the person rents but didn't say if the contract is registered).",
        "input_schema": {
            "type": "object",
            "properties": {"service_id": {"type": "string", "description": "An id from list_services, e.g. 'carta-identita'"}},
            "required": ["service_id"],
        },
    },
    {
        "name": "get_checklist",
        "description": (
            "Get the requirements that apply to this citizen's case, each with its source_id, a verbatim quote and the date it was verified. "
            "Pass the answers you have so far; 'still_to_ask' lists, in the order to ask them, only the questions that still change "
            "the answer (none that nothing in this case depends on). 'routes' says where the answers lead, each link with its source_id: "
            "'stop' (ends_case: this person cannot do the procedure here; say so with the items' sources, give services[].official_url, "
            "never booking advice), 'home' (the home service: give its form in links, not the booking page), 'desk' with links of its "
            "own (e.g. the PIN/PUK duplicate booking: give those, not the general booking page), 'walk-in' (no appointment needed), "
            "'info' (no visit needed: answer the question). "
            "Never state a requirement that is not in this result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "answers": {
                    "type": "object",
                    "description": "Deciding-question id -> chosen option, e.g. {\"motivo\": \"smarrimento-furto\"}",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["service_id"],
        },
    },
    {
        "name": "get_form_guide",
        "description": (
            "For a service sent online (has_form_guide in get_service): how to fill in the City's online application "
            "for this case. Returns the sections of the City's Modulistica page in order, the checklist items that go "
            "in each section, the City's own wording for the citizen's housing situation, and how to send the files. "
            "Pass the answers you have. Use it when the checklist is complete, to tell the person where each file goes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "answers": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["service_id"],
        },
    },
    {
        "name": "find_offices",
        "description": "Find City registry offices (open dataset ds549): address, hours, booking notes, and any known data issues. Filter by neighbourhood name, Municipio number, or nearest to a point.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area": {"type": "string", "description": "Neighbourhood or street, e.g. 'Isola', 'Bovisa'"},
                "municipio": {"type": "integer", "minimum": 1, "maximum": 9},
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "limit": {"type": "integer", "default": 3},
            },
        },
    },
    {
        "name": "get_source",
        "description": "Get the title, URL, publisher and retrieval date of a source_id, to cite it.",
        "input_schema": {
            "type": "object",
            "properties": {"source_id": {"type": "string"}},
            "required": ["source_id"],
        },
    },
    {
        "name": "search_official_pages",
        "description": search.TOOL["description"] + (
            " The result also gives the service's official page (official_page: url and source_id) to link, and cite, "
            "when no passage answers. Without service_id, the conversation's service is searched."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": ("The question, as the person asks it or reworded in Italian, "
                                                             "without names, tax codes, document numbers or addresses")},
                "service_id": {"type": "string", "description": "e.g. 'carta-identita' (optional: defaults to the conversation's service)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_source",
        "description": (
            "Read one saved official page in full, verbatim, in page order: its passages (passage_id, heading, text), with title, "
            "publisher, url, the page's own date (updated_at) and the date it was saved (saved_at). Use it when a passage from "
            "search_official_pages is relevant but incomplete (a list that continues, a rule with exceptions further down). "
            "At most ~12,000 characters: 'truncated' is true when the page goes on."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"source_id": {"type": "string", "description": "A source_id from search_official_pages or another tool"}},
            "required": ["source_id"],
        },
    },
]


def read_source(source_id: str, max_chars: int = READ_SOURCE_MAX_CHARS) -> dict:
    """The saved page of one source, verbatim, by passage (the read_source tool).

    {source_id, title, publisher, url, updated_at, saved_at, passages: [{passage_id, heading,
    text}], truncated}; passages stop before max_chars characters of text (the first one is
    always given). A source with no saved text page (an open dataset, a file) has no passages
    and a note; an unknown source_id gives {"error": ...}.
    """
    row = kb.sources().get(source_id)
    passages = search.passages_for(source_id)
    if not row and not passages:
        return {"error": "Unknown source_id"}
    row = row or {}
    first = passages[0] if passages else {}
    out: dict = {
        "source_id": source_id,
        "title": first.get("title") or row.get("title", ""),
        "publisher": first.get("publisher") or row.get("publisher", ""),
        "url": first.get("url") or row.get("url", ""),
        "updated_at": first.get("updated_at", ""),
        "saved_at": first.get("saved_at") or row.get("retrieved_at", ""),
        "passages": [],
        "truncated": False,
    }
    used = 0
    for p in passages:
        if out["passages"] and used + len(p["text"]) > max_chars:
            out["truncated"] = True
            break
        out["passages"].append({"passage_id": p["passage_id"], "heading": p["heading"], "text": p["text"]})
        used += len(p["text"])
    if not passages:
        out["note"] = "No saved text page for this source (open data or a file): nothing to quote from it."
    elif out["truncated"]:
        out["note"] = "The page goes on: search_official_pages with a narrower query finds its other passages."
    return out


def run_tool(name: str, args: dict, *, service_id: str | None = None, lang: str | None = None) -> str:
    """Run one tool and return the JSON string for its tool_result (errors too, as {"error"}).

    `service_id` is the conversation's service: search_official_pages searches it when its
    input names none. `lang` is passed to the search (passages in that language get a small
    boost); the agent leaves it out so the City's Italian pages are not outranked.
    """
    if name == "search_official_pages":
        query_args = dict(args or {})
        known = set(kb.list_service_ids())
        asked = query_args.get("service_id")
        if asked and not (isinstance(asked, str) and asked in known):  # "cie", 123, ["x"], "../x": not an id
            query_args.pop("service_id")
            out = json.loads(search.run_tool({**query_args, **({"service_id": service_id} if service_id in known else {})},
                                             lang=lang))
            if isinstance(out, dict) and "error" not in out:
                out["service_note"] = (f"Unknown service_id {str(asked)[:40]!r}: searched "
                                       + (f"'{service_id}'" if service_id in known else "all saved pages")
                                       + "; valid ids: " + ", ".join(sorted(known)))
            return json.dumps(out, ensure_ascii=False)
        if not query_args.get("service_id") and service_id in known:
            query_args["service_id"] = service_id
        return search.run_tool(query_args, lang=lang)
    try:
        if name == "list_services":
            result = kb.list_services()
        elif name == "get_service":
            result = kb.get_service(args["service_id"]) or {"error": "Unknown service_id"}
        elif name == "get_checklist":
            result = kb.checklist(args["service_id"], args.get("answers"))
        elif name == "get_form_guide":
            result = kb.form_guide(args["service_id"], args.get("answers"))
        elif name == "find_offices":
            result = kb.find_offices(args.get("area"), args.get("municipio"),
                                     args.get("lat"), args.get("lon"), args.get("limit", 3))
        elif name == "get_source":
            result = kb.get_source(args["source_id"]) or {"error": "Unknown source_id"}
        elif name == "read_source":
            result = read_source(str(args.get("source_id") or ""))
        else:
            result = {"error": f"Unknown tool {name}"}
    except Exception as e:  # report errors back to Claude instead of crashing
        result = {"error": f"Tool error: {e}"}
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    for t in TOOLS:
        print(t["name"])
    print(run_tool("get_checklist", {"service_id": "carta-identita", "answers": {"motivo": "smarrimento-furto"}})[:600])
