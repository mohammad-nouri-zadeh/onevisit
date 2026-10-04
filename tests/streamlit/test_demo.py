"""Demo mode: Claude's sentences are recorded, every fact is computed live from kb."""

from __future__ import annotations

import pytest

from onevisit import demo, kb, outcomes, validator

PERSONAS = list(demo.personas())


@pytest.mark.parametrize("persona_id", PERSONAS)
@pytest.mark.parametrize("lang", ["it", "en", "ar"])
def test_persona_plays_to_the_end_with_live_data(persona_id, lang):
    state, turns = demo.play(persona_id, lang)
    assert state["done"]
    # the checklist shown is exactly what kb computes for these answers
    live = kb.checklist(state["service_id"], state["answers"])
    assert state["checklist"]["requirements"] == live["requirements"]
    assert live["requirements"], "the demo should end with at least one verified requirement"
    known = set(kb.sources())
    for turn in turns:
        assert turn["check"]["ok"], turn["check"]
        assert turn["demo"] is True
        assert set(turn["cited"]) <= known
        assert set(turn["cited"]) <= set(state["read"])  # only sources a tool returned


@pytest.mark.parametrize("persona_id", PERSONAS)
def test_scripted_text_states_a_requirement_only_as_written_in_the_data_with_its_source(persona_id):
    """The templates never state a rule; the urgent options are the verified texts, each with
    its source."""
    state, turns = demo.play(persona_id, "it")
    texts = " ".join(t["text"] for t in turns)
    for req in kb.checklist(state["service_id"], state["answers"])["requirements"]:
        if req["text_it"] in texts:
            assert req.get("urgent_lead") and f"{req['text_it']} [{req['source_id']}]" in texts, (
                req["id"]
            )
        if req.get("text_en"):
            assert req["text_en"] not in texts


def test_first_turn_produces_a_checklist_and_asks_only_what_changes_it():
    state, user_text, reply = demo.start_persona("cie-isola", "en")
    assert user_text.startswith("I lost my ID card")
    # nothing is listed before the residence answer, which decides whether Milan issues the card
    assert not state["checklist"]["requirements"] and state["pending"] == "residenza"
    assert [s["tool"] for s in reply["trace"]][:3] == [
        "list_services",
        "get_service",
        "get_checklist",
    ]
    nxt = demo.answer(state, "Resident in Milan")
    assert state["checklist"]["requirements"] and nxt["check"]["ok"]
    if state["pending"]:
        assert state["pending"] in state["checklist"]["still_to_ask"]
        assert reply["options"] and len(reply["options"]) == len(reply["option_ids"])
    assert state["answers"].get("motivo") == "smarrimento-furto"  # understood from the message
    assert state["offices"] and "ds549" in reply["cited"]


def test_arabic_persona_answers_in_arabic():
    _, user_text, reply = demo.start_persona("cairo-residenza", "ar")
    assert validator.fold("القاهرة") in validator.fold(user_text)
    assert any("\u0600" <= ch <= "\u06ff" for ch in reply["text"])


def test_free_text_in_demo_keeps_the_state():
    state, _, _ = demo.start_persona("cie-isola", "it")
    before = dict(state["answers"])
    out = demo.answer(state, "blah blah")
    assert out["trace"] == [] and state["answers"] == before
    assert (
        "replica" in out["text"].lower() and "claude" in out["text"].lower()
    )  # says what the replay can't do


def test_typed_answer_matching_an_option_is_understood():
    state, _, reply = demo.start_persona("cie-isola", "en")
    if not state["pending"]:
        pytest.skip("nothing left to ask with the current data")
    label = reply["options"][0]
    out = demo.answer(state, label.upper())
    assert out["trace"], "a matched option runs the tools again"


def test_appointment_from_the_booking_link():
    state, reply = demo.start_appointment("carta-identita", "ds549-11", "2030-01-15", "it")
    assert "15/01/2030" in reply["text"] and "Largo De Benedetti 1" in reply["text"]
    assert state["office_id"] == "ds549-11" and state["pending"] == "residenza"
    assert reply["check"]["ok"]
    demo.answer(state, "Residente a Milano")
    demo.answer(state, "Rinnovo")  # what the appointment is for
    assert state["checklist"]["requirements"]


def test_idle_reply_states_nothing():
    reply = demo.idle("en")
    assert reply["trace"] == [] and reply["check"]["ok"]


def test_recorded_drafts_exist_for_the_groups_that_reach_the_office():
    for group in outcomes.groups():
        if group["over_threshold"]:
            draft = demo.draft(group)
            assert draft and draft.startswith("BOZZA DA APPROVARE")
