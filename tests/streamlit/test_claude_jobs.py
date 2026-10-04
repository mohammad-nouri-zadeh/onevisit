"""Claude's other jobs, with a fake client: the next 3 actions, report classification without
personal data, the evaluation runner; and the demo's keyword reading of a typed message."""

from __future__ import annotations

import json

import pytest
from fakes import FakeClient, Response, text, tool

from onevisit import demo, evaluate, kb, outcomes, plan, validator

RESIDENCE = "iscrizione-anagrafica-extra-ue"
CAIRO = {"permesso": "ricevuta-lavoro", "famiglia": "solo", "alloggio": "affitto"}


def test_claude_orders_the_next_actions_and_the_check_drops_what_is_not_in_the_checklist():
    reply = {
        "actions": [
            {
                "requirement_ids": ["contratto-soggiorno", "ricevuta-poste"],
                "action": "Scansiona contratto e ricevuta.",
                "why": "Servono per la sezione sulla cittadinanza.",
            },
            {
                "requirement_ids": ["certificato-inventato"],
                "action": "Porta il certificato.",
                "why": "",
            },
            {
                "requirement_ids": ["codice-fiscale"],
                "action": "Tieni pronto il codice fiscale: sei in regola.",
                "why": "",
            },
            {
                "requirement_ids": ["alloggio-affitto"],
                "action": "Scansiona il contratto d'affitto.",
                "why": "Ultimo file.",
            },
        ]
    }
    fake = FakeClient([text(json.dumps(reply))])
    result = plan.claude_actions(RESIDENCE, CAIRO, "it", client=fake)
    assert [a["requirement_ids"] for a in result["actions"]] == [
        ["contratto-soggiorno", "ricevuta-poste"],
        ["alloggio-affitto"],
    ]
    assert result["actions"][0]["source_ids"] == [
        "residenza-estero-extraue"
    ]  # sources from the items, not from Claude
    reasons = [r for x in result["rejected"] for r in x["reasons"]]
    assert "unknown_requirement:certificato-inventato" in reasons
    assert any(r.startswith("eligibility_claim") for r in reasons)
    call = fake.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    prompt = call["messages"][0]["content"]
    assert (
        "contratto-soggiorno" in prompt and "consenso-stato-famiglia" not in prompt
    )  # only this case's items


def test_next_actions_skip_what_is_ticked_and_a_refusal_shows_nothing():
    fake = FakeClient([Response([], stop_reason="refusal")])
    assert plan.claude_actions(RESIDENCE, CAIRO, "en", client=fake)["actions"] == []
    first = plan.fallback_actions(RESIDENCE, CAIRO, "en")["actions"]
    ticked = {first[0]["requirement_ids"][0]}
    again = plan.fallback_actions(RESIDENCE, CAIRO, "en", ticked=ticked)["actions"]
    assert again[0]["requirement_ids"] != first[0]["requirement_ids"] and len(again) == 3


def test_personal_details_never_reach_claude():
    note = (
        "Sono RSSMRA80A01F205X, scrivetemi a nome.prova@example.org o al +39 000 000 0000: "
        "il 12/09/2026 mi hanno chiesto il contratto registrato."
    )
    clean, removed = outcomes.scrub(note)
    assert {"codice_fiscale", "email", "telefono", "data"} <= set(removed)
    for value in ("RSSMRA80A01F205X", "nome.prova@example.org", "000 000 0000", "12/09/2026"):
        assert value not in clean
    fake = FakeClient(
        [text('{"cause": "pagina-incompleta", "summary_it": "x", "summary_en": "y"}')]
    )
    outcomes.classify(RESIDENCE, "missing", note, client=fake)
    prompt = fake.calls[0]["messages"][0]["content"]
    assert (
        "RSSMRA80A01F205X" not in prompt
        and "example.org" not in prompt
        and "contratto registrato" in prompt
    )


def test_recorded_classification_only_for_the_examples():
    examples = outcomes.example_notes("en")
    assert examples and outcomes.recorded_classification(examples[0])["cause"] in outcomes.CAUSES
    assert outcomes.recorded_classification("something else entirely") is None


@pytest.mark.parametrize(
    "message,service,answers",
    [
        (
            "Ho perso la carta d'identità e parto il mese prossimo. Abito all'Isola.",
            "carta-identita",
            {"motivo": "smarrimento-furto", "eta": "adulto"},
        ),
        (
            "Mi carta de identidad caducó y tengo que renovarla. Soy peruano y vivo en Bovisa.",
            "carta-identita",
            {"motivo": "rinnovo", "eta": "adulto", "cittadinanza": "extra-ue"},
        ),
        (
            # a message in Chinese, with Chinese punctuation on purpose
            "我们从中国来，我和妻子还有儿子。我有居留许可，我们租了一套公寓。怎么办理居住登记？",  # noqa: RUF001
            RESIDENCE,
            {"permesso": "permesso", "famiglia": "con-familiari"},
        ),
        (
            "I'm a student waiting for my first study permit and I rent a room. "
            "How do I register my residence?",
            RESIDENCE,
            {"permesso": "altro"},
        ),
        (
            "I have my residence permit and I rent a flat with a contract not registered yet: "
            "how do I register my residence?",
            RESIDENCE,
            {"permesso": "permesso", "alloggio": "affitto"},
        ),
        ("Devo fare il cambio di residenza, mi sono trasferito da Torino", "cambio-residenza", {}),
        (
            "Sono italiana, vivo in affitto e devo cambiare residenza",
            "cambio-residenza",
            {"cittadinanza": "italiana", "alloggio": "non-proprietario"},
        ),
    ],
)
def test_demo_reads_a_typed_message_with_keywords(message, service, answers):
    state, reply = demo.start_text(message, "it")
    assert state["service_id"] == service and state["answers"] == answers
    assert reply["routing"] == "keywords" and reply["check"]["ok"]
    if service == "carta-identita":  # where the person is resident decides everything: asked first
        assert state["pending"] == "residenza" and "residenza" in state["checklist"]["still_to_ask"]
    else:
        assert state["checklist"]["requirements"]


def test_demo_asks_which_procedure_when_the_words_say_nothing():
    state, reply = demo.start_text("buongiorno, mi serve una mano", "it")
    assert state["pending"] == demo.SERVICE_CHOICE and len(reply["options"]) == len(
        kb.list_services()
    )
    nxt = demo.answer(state, reply["options"][0])
    assert state["service_id"] == reply["option_ids"][0] and nxt["check"]["ok"]


def test_typed_answer_to_a_pending_question():
    state, _, _ = demo.start_persona("cairo-residenza", "en")
    assert state["pending"] == "permesso"
    demo.answer(
        state,
        "I'm waiting for my first permit, I signed the contratto di soggiorno and have the receipt",
    )
    assert state["answers"]["permesso"] == "ricevuta-lavoro"


def test_student_case_shows_what_the_sources_do_not_cover():
    state, _turns = demo.play("studente-studio", "es")
    assert state["done"] and "documenti-altri-permessi" in state["checklist"]["not_yet_verified"]
    assert "caso-non-coperto" in {r["id"] for r in state["checklist"]["requirements"]}


def test_evaluation_runner_scores_a_scenario_with_a_fake_claude():
    scenario = next(s for s in evaluate.scenarios() if s["id"] == "cie-smarrimento-it")
    fake = FakeClient(
        [
            tool("get_service", service_id="carta-identita"),
            tool(
                "get_checklist",
                service_id="carta-identita",
                answers={"residenza": "milano", "motivo": "smarrimento-furto", "eta": "adulto"},
            ),
            text(
                "Senza appuntamento, con la denuncia, puoi andare a una sede anagrafica [cie]. "
                "La verifica finale spetta all'operatore allo sportello."
            ),
        ]
    )
    result = evaluate.run_one(scenario, fake)
    assert result.passed, result.failures
    assert result.tool_calls == 2 and result.turns == 1 and result.blocked == 0
    md = evaluate.report([result], "fake-model")
    assert "1/1 scenarios passed" in md and "`cie-smarrimento-it` | pass" in md


def test_evaluation_runner_counts_a_blocked_reply_and_its_regeneration():
    scenario = next(s for s in evaluate.scenarios() if s["id"] == "sei-in-regola-it")
    fake = FakeClient(
        [
            tool(
                "get_checklist",
                service_id="carta-identita",
                answers={
                    "residenza": "milano",
                    "motivo": "smarrimento-furto",
                    "eta": "adulto",
                    "cittadinanza": "italiana",
                },
            ),
            text("Porta la denuncia [cie]. Hai una domanda?"),
            text("Sei in regola e il rilascio è garantito [cie]."),  # blocked by the validator
            text(
                "Porta la denuncia [cie]; la verifica finale spetta all'operatore allo sportello."
            ),
        ]
    )
    result = evaluate.run_one(scenario, fake)
    assert result.blocked == 1 and result.regenerated == 1 and result.fallbacks == 0
    assert result.passed, result.failures  # the blocked words never reached the citizen


def test_every_scenario_file_loads():
    found = evaluate.scenarios()
    assert len(found) == len(list(evaluate.EVAL_DIR.glob("*.yaml"))) >= 18
    assert all(s["expect"] and s["messages"] for s in found)
    known = set(kb.list_services()[i]["id"] for i in range(len(kb.list_services())))
    assert all(s["expect"].get("service") in known | {None} for s in found)


def test_renting_without_saying_if_the_contract_is_registered_asks_exactly_that():
    """ "I rent a room" alone: the demo asks the narrow question with two options, and each
    answer gives one rental-contract item, never both (the City page and YesMilano cover
    different cases)."""
    state, reply = demo.start_text(
        "I just arrived from Cairo for work, I have my residence permit, I live alone and "
        "I rent a room. How do I register my residence?",
        "en",
    )
    assert state["service_id"] == RESIDENCE and state["pending"] == "alloggio"
    assert reply["option_ids"] == ["affitto-registrato", "affitto"]
    assert "already registered" in reply["text"]
    for choice, item in (
        ("affitto-registrato", "alloggio-affitto-registrazione"),
        ("affitto", "alloggio-affitto"),
    ):
        cl = kb.checklist(
            RESIDENCE, {"permesso": "permesso", "famiglia": "solo", "alloggio": choice}
        )
        rental = [r["id"] for r in kb.to_upload(cl) if r["id"].startswith("alloggio-affitto")]
        assert rental == [item]
    nxt = demo.answer(state, reply["options"][1])
    assert state["answers"]["alloggio"] == "affitto" and nxt["check"]["ok"]


def test_residence_without_where_from_asks_which_of_the_two_procedures():
    state, reply = demo.start_text("Devo fare la residenza a Milano", "it")
    assert state["pending"] == demo.SERVICE_CHOICE
    assert reply["option_ids"] == [RESIDENCE, "cambio-residenza"]
    demo.answer(state, reply["options"][1])
    assert state["service_id"] == "cambio-residenza"


def test_a_move_from_another_comune_is_not_routed_to_the_procedure_for_arrivals_from_abroad():
    state, reply = demo.start_text(
        "Devo fare il cambio di residenza, mi sono trasferito da Torino", "it"
    )
    assert state["service_id"] == "cambio-residenza"
    assert "permesso" not in validator.fold(
        reply["text"]
    )  # no residence-permit question for an internal move
    assert "anpr-cambio-residenza" in reply["cited"] or "cambio-residenza" in reply["cited"]
    assert state["pending"] == "cittadinanza" and reply["check"]["ok"]
    for option in ("Italiana", "Non è mia (affitto, ospite o altro)", "Da solo/a"):
        out = demo.answer(state, option)
    assert state["done"] and out["check"]["ok"]
    links = kb.service_links("cambio-residenza")
    assert links["online_form_url"]["url"] in out["text"]  # sent online on the national ANPR site
    ids = {r["id"] for r in state["checklist"]["requirements"]}
    assert {"online-spid-cie", "entro-20-giorni", "estremi-contratto", "invio-diretto"} <= ids
    assert "permesso-extra-ue" not in ids
