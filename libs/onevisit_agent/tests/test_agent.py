"""Test del ciclo dell'agente con il client finto (storie C3, B1-B4). Nessuna rete."""

import dataclasses
import json
import re

from onevisit_agent import Capabilities, ClaudeClientError, SessionState, load_system_prompt
from onevisit_agent.language import parse_reply
from onevisit_agent.testing import FakeClaudeClient, text_response, tool_response

WEB = Capabilities(channel="web", buttons=True)
FAKE_CF = "RSSMRA80A01F205X"
FAKE_EMAIL = "mario.test@example.org"


def _tool_results(client: FakeClaudeClient, call_index: int) -> list[dict[str, object]]:
    last = client.calls[call_index].messages[-1]
    content = last["content"]
    assert isinstance(content, list)
    return [b for b in content if b.get("type") == "tool_result"]


def test_tool_dispatch_calls_catalog_with_right_arguments(make_agent, catalog) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            tool_response(
                (
                    "build_checklist",
                    {
                        "service_id": "carta-identita",
                        "answers": {"motivo": "rinnovo", "eta": "boh"},
                    },
                )
            ),
            text_response("<lang>it</lang>Serve l'appuntamento [fonte: ds549]."),
        ]
    )

    result = make_agent(client).run_turn(SessionState(), "rinnovo carta", WEB)

    assert ("checklist", ("carta-identita", {"motivo": "rinnovo"})) in catalog.calls
    payload = json.loads(str(_tool_results(client, 1)[0]["content"]))
    assert payload["items"][0]["source_id"] == "ds549"
    assert payload["items"][0]["quote"]
    assert result.blocked is False


def test_get_office_returns_source_date_and_stale_warning(make_agent, catalog) -> None:  # type: ignore[no-untyped-def]
    catalog.stale = True
    client = FakeClaudeClient(
        script=[
            tool_response(("get_office", {"municipio": 1})),
            text_response("<lang>it</lang>Vai in via Larga 12 [fonte: ds549]."),
        ]
    )

    make_agent(client).run_turn(SessionState(), "dove vado?", WEB)

    office = json.loads(str(_tool_results(client, 1)[0]["content"]))["offices"][0]
    assert office["address"] == "via Larga 12"
    assert office["source"]["verified_at"] == "2026-08-01"
    assert office["source"]["stale_warning"] is True
    assert ("offices", (None, 1)) in catalog.calls


def test_blocked_reply_is_regenerated_once(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            text_response("<lang>it</lang>Sei in regola!"),
            text_response("<lang>it</lang>Il desk decide; è la prima carta?"),
        ]
    )

    result = make_agent(client).run_turn(SessionState(), "sono in regola?", WEB)

    assert result.blocked is False
    assert result.messages == ["Il desk decide; è la prima carta?"]
    note = client.calls[1].messages[-1]["content"][0]["text"]
    assert "forbidden_phrase:in regola" in note


def test_twice_blocked_reply_returns_fallback_with_official_link(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            text_response("<lang>en</lang>You are eligible."),
            text_response("<lang>en</lang>Guaranteed, see [fonte: made-up]."),
        ]
    )

    result = make_agent(client).run_turn(SessionState(language="en"), "am I ok?", WEB)

    assert result.blocked is True
    assert "https://www.comune.milano.it/servizi" in result.messages[0]
    assert result.messages[0].startswith("Sorry")
    assert result.state.history[-1]["role"] == "assistant"


def test_model_error_returns_courteous_fallback(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(script=[ClaudeClientError("APITimeoutError")])

    result = make_agent(client).run_turn(SessionState(), "ciao", WEB)

    assert "https://www.comune.milano.it/servizi" in result.messages[0]
    assert result.messages[0].startswith("Mi dispiace")
    assert result.blocked is False


def test_reply_without_citation_after_facts_is_regenerated(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            tool_response(("build_checklist", {"service_id": "carta-identita", "answers": {}})),
            text_response("<lang>it</lang>Serve l'appuntamento."),
            text_response("<lang>it</lang>Serve l'appuntamento [fonte: ds549]."),
        ]
    )

    result = make_agent(client).run_turn(SessionState(), "cosa porto?", WEB)

    assert result.messages == ["Serve l'appuntamento [fonte: ds549]."]
    assert len(client.calls) == 3


def test_system_prompt_forbids_identity_data_and_eligibility() -> None:
    prompt = load_system_prompt()

    assert "Prompt version:" in prompt
    assert "Never ask for name, surname, codice fiscale" in prompt
    assert "Never say or imply that the citizen is eligible" in prompt
    assert "[fonte: <source_id>]" in prompt


def test_case_state_has_no_free_text_after_personal_data(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            tool_response(
                (
                    "identify_case",
                    {
                        "service_id": "carta-identita",
                        "variant": FAKE_CF,
                        "answers": {"motivo": "smarrimento-furto", "eta": FAKE_EMAIL, FAKE_CF: "x"},
                        "deadline_days": 30,
                        "category": "extra-ue",
                    },
                )
            ),
            text_response("<lang>it</lang>Grazie, non mi servono questi dati. È per un adulto?"),
        ]
    )
    message = f"ho perso la carta, il mio codice fiscale è {FAKE_CF} e la mail {FAKE_EMAIL}"

    result = make_agent(client).run_turn(SessionState(), message, WEB)

    dumped = result.state.case.model_dump_json()
    assert FAKE_CF not in dumped
    assert FAKE_EMAIL not in dumped
    assert result.state.case.answers == {"motivo": "smarrimento-furto"}
    assert result.state.case.variant == "smarrimento-furto"
    assert result.state.case.deadline_days == 30
    assert [e.kind for e in result.events] == ["case_identified"]
    assert FAKE_CF not in json.dumps([e.data for e in result.events])


def test_language_marker_is_parsed_and_stripped() -> None:
    parsed = parse_reply("<lang>es</lang>Hola, ¿es tu primera tarjeta?<quick>Sí | No</quick>")

    assert parsed.language == "es"
    assert parsed.text == "Hola, ¿es tu primera tarjeta?"
    assert parsed.quick_replies == ["Sí", "No"]


def test_turn_language_comes_from_marker_and_defaults_to_browser(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(script=[text_response("Hello!"), text_response("<lang>fr</lang>Ok")])
    agent = make_agent(client)
    caps = Capabilities(browser_language="en-GB,en;q=0.9")

    first = agent.run_turn(SessionState(), "hi", caps)
    second = agent.run_turn(first.state, "bonjour, je voudrais une carte", caps)

    assert first.language == "en"
    assert second.language == "fr"
    assert second.state.language == "fr"


def test_appointment_lead_time_warning(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            tool_response(("identify_case", {"service_id": "carta-identita"})),
            tool_response(
                (
                    "record_appointment",
                    {"date": "2026-10-13", "time": "09:30", "office_id": "ds549-01"},
                )
            ),
            text_response("<lang>it</lang>Attenzione: la traduzione richiede tempo [fonte: cie]."),
        ]
    )

    result = make_agent(client).run_turn(SessionState(), "ho appuntamento il 13", WEB)

    payload = json.loads(str(_tool_results(client, 2)[0]["content"]))
    assert payload["days_left"] == 10
    assert payload["lead_time_warnings"] == [
        {"requirement_id": "traduzione", "lead_time_days": 20, "source_id": "cie"}
    ]
    assert result.state.case.appointment is not None
    assert result.state.case.appointment.office_id == "ds549-01"
    assert any(e.kind == "appointment_recorded" for e in result.events)


def test_request_contact_needs_appointment(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            tool_response(("request_contact", {})),
            text_response("<lang>it</lang>Prima dimmi la data dell'appuntamento."),
        ]
    )

    result = make_agent(client).run_turn(SessionState(), "mandami promemoria", WEB)

    payload = json.loads(str(_tool_results(client, 1)[0]["content"]))
    assert payload == {"error": "no_appointment_recorded"}
    assert result.events == []


def test_missing_procedure_sets_flag_and_emits_event(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            tool_response(
                (
                    "report_missing_procedure",
                    {"summary_generalized": "richiesta di contrassegno per disabili"},
                )
            ),
            text_response("<lang>it</lang>Non è ancora nel catalogo: vedi il sito del Comune."),
        ]
    )

    result = make_agent(client).run_turn(SessionState(), "contrassegno disabili", WEB)

    assert result.state.case.missing_procedure is True
    assert result.events[0].kind == "missing_procedure"
    assert result.events[0].data["summary_generalized"] == "richiesta di contrassegno per disabili"


def test_missing_procedure_summary_with_personal_data_is_dropped(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            tool_response(
                (
                    "report_missing_procedure",
                    {"summary_generalized": f"permesso ZTL per {FAKE_EMAIL}"},
                )
            ),
            text_response("<lang>it</lang>Non è nel catalogo."),
        ]
    )

    result = make_agent(client).run_turn(SessionState(), "ztl", WEB)

    assert result.events[0].data["summary_generalized"] is None


def test_unknown_service_is_a_tool_error_not_a_crash(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            tool_response(("get_procedure", {"service_id": "passaporto"})),
            text_response("<lang>it</lang>Non lo trovo nel catalogo."),
        ]
    )

    make_agent(client).run_turn(SessionState(), "passaporto", WEB)

    result_block = _tool_results(client, 1)[0]
    assert result_block["is_error"] is True


def test_prompt_caching_on_system_and_tools(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(script=[text_response("<lang>it</lang>Ciao")])

    make_agent(client).run_turn(SessionState(), "ciao", WEB)

    call = client.calls[0]
    assert call.system[-1]["cache_control"] == {"type": "ephemeral"}
    assert "carta-identita" in call.system[-1]["text"]
    assert call.tools is not None
    assert call.tools[-1]["cache_control"] == {"type": "ephemeral"}
    names = [t["name"] for t in call.tools]
    assert "book" not in " ".join(names)
    assert len(names) == 8


def test_log_has_no_message_text(make_agent, caplog) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            text_response("<lang>it</lang>Sei idoneo"),
            text_response("<lang>it</lang>Sei idoneo"),
        ]
    )

    with caplog.at_level("DEBUG"):
        make_agent(client).run_turn(SessionState(), f"cf {FAKE_CF}", WEB)

    assert FAKE_CF not in caplog.text
    assert not re.search(r"Sei idoneo", caplog.text)


def test_reply_without_citation_after_get_procedure_is_regenerated(make_agent) -> None:  # type: ignore[no-untyped-def]
    client = FakeClaudeClient(
        script=[
            tool_response(("get_procedure", {"service_id": "carta-identita"})),
            text_response("<lang>it</lang>Prima prenota, poi vai allo sportello."),
            text_response("<lang>it</lang>Prima prenota, poi vai allo sportello [fonte: ds549]."),
        ]
    )

    result = make_agent(client).run_turn(SessionState(), "come faccio?", WEB)

    assert result.messages == ["Prima prenota, poi vai allo sportello [fonte: ds549]."]
    assert len(client.calls) == 3


def test_identify_case_asks_only_what_the_catalog_still_needs(make_agent, catalog) -> None:  # type: ignore[no-untyped-def]
    """still_to_ask is the catalog's (questions something still possible depends on), not every
    unanswered question: as onevisit/kb.py."""
    original = catalog.checklist
    catalog.checklist = lambda service_id, answers: dataclasses.replace(
        original(service_id, answers), still_to_ask=()
    )
    client = FakeClaudeClient(
        script=[
            tool_response(
                ("identify_case", {"service_id": "carta-identita", "answers": {"motivo": "prima"}})
            ),
            text_response("<lang>it</lang>Bene."),
        ]
    )
    make_agent(client).run_turn(SessionState(), "prima carta", WEB)
    payload = json.loads(str(_tool_results(client, 1)[0]["content"]))
    assert payload["still_to_ask"] == []  # "eta" is unanswered, but nothing depends on it here


def test_build_checklist_gives_the_routes_with_their_sources(make_agent, catalog) -> None:  # type: ignore[no-untyped-def]
    stop = {
        "question": "residenza",
        "answer": "altra-regione",
        "route": "stop",
        "ends_case": True,
        "services": [
            {
                "id": "x",
                "official_url": {"url": "https://www.comune.milano.it/x", "source_id": "cie"},
            }
        ],
    }
    catalog.routes = lambda service_id, answers: [stop]
    client = FakeClaudeClient(
        script=[
            tool_response(("build_checklist", {"service_id": "carta-identita", "answers": {}})),
            text_response("<lang>it</lang>Qui non si fa [fonte: cie]."),
        ]
    )
    make_agent(client).run_turn(SessionState(), "sono residente a Roma", WEB)
    payload = json.loads(str(_tool_results(client, 1)[0]["content"]))
    assert payload["routes"] == [stop]
