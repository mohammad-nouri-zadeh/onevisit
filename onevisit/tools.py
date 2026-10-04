"""Tool definitions for the Claude API, backed by onevisit/kb.py.

The agent team plugs these into their loop:

    from onevisit.tools import TOOLS, run_tool
    response = client.messages.create(..., tools=TOOLS, ...)
    # for each tool_use block:  run_tool(block.name, block.input)  -> string for the tool_result

Same shape as the hackathon starter (starter/runs_on_claude.py).
"""
import json

from onevisit import kb

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
            "Pass the answers you have so far; 'still_to_ask' lists the questions that would change the list. "
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
]


def run_tool(name: str, args: dict) -> str:
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
        else:
            result = {"error": f"Unknown tool {name}"}
    except Exception as e:  # report errors back to Claude instead of crashing
        result = {"error": f"Tool error: {e}"}
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    for t in TOOLS:
        print(t["name"])
    print(run_tool("get_checklist", {"service_id": "carta-identita", "answers": {"motivo": "smarrimento-furto"}})[:600])
