"""The complete ID card (CIE) workflow in the app: residence, home service and damaged cards.

The catalog asks where the person is resident and whether they can come to the desk; the
demo, its keyword rules and the evaluation scenarios must follow it.
"""

from __future__ import annotations

import pathlib

import pytest

from onevisit import demo, evaluate, kb

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"

CIE = "carta-identita"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "La mia carta d'identità elettronica è rovinata e il chip non funziona più.",
            {"motivo": "deteriorata"},
        ),
        ("My ID card is damaged", {"motivo": "deteriorata"}),
        (
            "Sono residente a Monza ma lavoro a Milano: posso rinnovare la carta d'identità?",
            {"motivo": "rinnovo", "residenza": "altro-comune-lombardia"},
        ),
        (
            "Sono residente a Roma ma domiciliato a Milano, la carta d'identità è scaduta",
            {"motivo": "rinnovo", "residenza": "domicilio-milano"},
        ),
        (
            "Sono iscritto all'AIRE di Milano e devo rinnovare la carta d'identità",
            {"motivo": "rinnovo", "residenza": "aire"},
        ),
        (
            "I'm not registered as a resident yet. Can I get an Italian ID card?",
            {"residenza": "non-residente"},
        ),
        (
            "Mia madre è allettata e la sua carta d'identità è scaduta.",
            {"motivo": "rinnovo", "presenza": "domicilio-salute"},
        ),
    ],
)
def test_keyword_rules_read_the_new_id_card_answers(message, expected):
    found = demo.understand(message)
    assert found["service_id"] == CIE
    for qid, value in expected.items():
        assert found["answers"].get(qid) == value, (qid, found["answers"])


def test_living_somewhere_is_not_read_as_being_resident():
    found = demo.understand("Ho perso la carta d'identità, abito all'Isola")
    assert "residenza" not in found["answers"] and found["area"] == "Isola"


def test_every_typed_answer_is_a_live_option():
    questions = {q["id"]: q for q in kb.get_service(CIE)["deciding_questions"] if q.get("options")}
    for qid in ("motivo", "residenza", "presenza"):
        for value, _ in demo._ANSWER_WORDS[qid]:
            assert value in questions[qid]["options"], (qid, value)


@pytest.mark.parametrize("persona_id", ["cie-isola", "cie-rinnovo-bovisa"])
def test_id_card_personas_end_with_every_question_answered(persona_id):
    state, turns = demo.play(persona_id, "en")
    cl = state["checklist"]
    assert not cl["still_to_ask"] and not cl["not_yet_verified"]
    assert state["answers"]["residenza"] == "milano"
    assert state["answers"]["presenza"] == "sportello"
    assert all(t["check"]["ok"] for t in turns)


def test_home_service_case_lists_the_form_and_its_attachments():
    answers = {
        "motivo": "rinnovo",
        "eta": "adulto",
        "cittadinanza": "italiana",
        "residenza": "milano",
        "presenza": "domicilio-salute",
    }
    ids = {r["id"] for r in kb.checklist(CIE, answers)["requirements"]}
    assert {"domicilio-servizio", "domicilio-form", "domicilio-certificato"} <= ids


def _reachable(requirement: dict, variant: str | None, questions: dict) -> bool:
    """The requirement can apply in a case whose answer to "motivo" is `variant`."""
    when = requirement.get("when") or {}
    assert "motivo" in questions
    return not variant or "motivo" not in when or variant in when["motivo"]


def test_id_card_eval_scenarios_name_existing_requirements_and_options():
    service = kb.get_service(CIE)
    questions = {q["id"]: q for q in service["deciding_questions"] if q.get("options")}
    by_id = {
        r["id"]: r for r in kb._services()[CIE]["requirements"] if r.get("status") == "verified"
    }
    cases = [s for s in evaluate.scenarios() if (s.get("expect") or {}).get("service") == CIE]
    assert len(cases) >= 10
    every_option = {o for q in questions.values() for o in q["options"]}
    for scenario in cases:
        expect = scenario["expect"]
        assert expect.get("variant") in every_option, scenario["id"]
        for rid in expect.get("requirements_include") or []:
            assert rid in by_id, (scenario["id"], rid)
            assert _reachable(by_id[rid], expect.get("variant"), questions), (scenario["id"], rid)


# ---- the reviewed cases: who can apply in Milan, how, and what each case must not be told ----

MILAN = {
    "residenza": "milano",
    "eta": "adulto",
    "cittadinanza": "italiana",
    "presenza": "sportello",
}
DESK_ONLY = {
    "su-appuntamento",
    "accettazione",
    "accettazione-obbligatoria",
    "costo",
    "foto-prima-del-check-in",
}


def _ids(answers: dict) -> set[str]:
    cl = kb.checklist(CIE, answers)
    assert not cl["still_to_ask"], cl["still_to_ask"]
    return {r["id"] for r in cl["requirements"]}


@pytest.mark.parametrize("residenza", ["altro-comune-lombardia", "non-residente"])
def test_someone_not_served_in_milan_gets_only_where_to_go(residenza):
    ids = _ids({**MILAN, "motivo": "rinnovo", "residenza": residenza})
    assert "solo-residenti" in ids
    assert not ids & (DESK_ONLY | {"tempi-consegna", "documento-precedente", "fototessera"})


def test_the_replay_gives_no_booking_link_to_someone_not_served_in_milan():
    state, reply = demo.start_text(
        "Sono residente a Monza e la mia carta d'identità è scaduta", "it"
    )
    while state.get("pending"):
        reply = demo.answer(state, reply["options"][0])
    assert state["answers"]["residenza"] == "altro-comune-lombardia"
    assert "anagrafecie" not in reply["text"] and "dossier per lo sportello" in reply["text"]
    assert "non si chiede a Milano" in reply["text"] and "cambio-di-residenza" in reply["text"]
    assert reply["check"]["ok"]


def test_home_service_has_no_desk_items_and_links_the_form_not_the_booking():
    answers = {**MILAN, "motivo": "rinnovo", "presenza": "domicilio-salute"}
    ids = _ids(answers)
    assert not ids & DESK_ONLY and "domicilio-pagamento" in ids
    state, reply = demo.start_text(
        "Mia madre è costretta a letto e la sua carta d'identità è scaduta", "it"
    )
    assert state["answers"]["presenza"] == "domicilio-salute"
    while state.get("pending"):
        reply = demo.answer(
            state,
            demo.option_label(MILAN.get(state["pending"], ""), "it")
            if state["pending"] in MILAN
            else reply["options"][0],
        )
    assert "SERVIZIO_ANAGRAFICO_DOMICILIO" in reply["text"] and "anagrafecie" not in reply["text"]
    assert reply["check"]["ok"]


def test_lost_pin_and_puk_has_its_own_route_and_booking_link():
    found = demo.understand("Ho perso il PIN e il PUK della carta d'identità")
    assert found["service_id"] == CIE and found["answers"]["motivo"] == "pin-puk"
    assert (
        demo.understand("Ho perso la carta d'identità e il PIN")["answers"]["motivo"]
        == "smarrimento-furto"
    )
    ids = _ids({**MILAN, "motivo": "pin-puk"})
    assert {
        "pin-puk-smarriti",
        "puk-recupero-app",
        "pin-nuovo-con-puk",
        "contatti-aggiornare",
    } <= ids
    assert not ids & ({"fototessera", "denuncia", "blocco-carta"} | DESK_ONLY)
    home = _ids({**MILAN, "motivo": "pin-puk", "presenza": "domicilio-salute"})
    assert "pin-puk-domicilio" in home and "pin-puk-smarriti" not in home
    routes = demo.routes(kb.get_service(CIE), {"motivo": "pin-puk"})
    assert any("richiesta-duplicato-pin-puk" in link["url"] for r in routes for link in r["links"])


def test_minors_get_the_minors_rules_not_the_adult_identification():
    ids = _ids({**MILAN, "motivo": "prima", "eta": "minore"})
    assert {"minori", "minori-un-genitore", "minori-neonati", "minori-impronte-firma"} <= ids
    assert not ids & {
        "altro-documento",
        "testimoni-prima",
        "testimoni",
        "impronte",
        "impronte-dita",
    }


def test_travel_items_only_for_italian_citizens():
    trips = {
        "viaggio-15-giorni",
        "viaggio-5-giorni",
        "provvisoria-estero",
        "smarrimento-estero-etd",
    }
    for citizenship in ("ue", "extra-ue"):
        ids = _ids({**MILAN, "motivo": "smarrimento-furto", "cittadinanza": citizenship})
        assert "espatrio-adulti-non-italiani" in ids and not ids & trips
    assert trips <= _ids({**MILAN, "motivo": "smarrimento-furto"})


def test_temporary_card_replaces_a_previous_card_only():
    assert "carta-provvisoria" not in _ids({**MILAN, "motivo": "prima"})
    assert "carta-provvisoria" in _ids({**MILAN, "motivo": "rinnovo"})


def test_chip_only_fault_is_free_and_needs_no_booking():
    ids = _ids({**MILAN, "motivo": "chip"})
    assert {"chip-segnalazione", "chip-difettoso"} <= ids and not ids & DESK_ONLY
    assert (
        demo.understand("Il chip della mia carta d'identità non funziona")["answers"]["motivo"]
        == "chip"
    )
    assert (
        demo.understand("La mia carta d'identità è rovinata e il chip non va")["answers"]["motivo"]
        == "deteriorata"
    )


def test_already_having_the_card_needs_no_visit():
    ids = _ids({**MILAN, "motivo": "gia-cie"})
    assert "cambio-indirizzo" in ids and not ids & (DESK_ONLY | {"fototessera"})
    assert (
        demo.understand("Ho cambiato indirizzo, devo rifare la carta d'identità?")["answers"][
            "motivo"
        ]
        == "gia-cie"
    )


def test_citizenship_is_not_read_from_where_something_happened():
    stolen_in_spain = demo.understand("Mi hanno rubato la carta d'identità in Spagna")["answers"]
    assert "cittadinanza" not in stolen_in_spain
    permit = demo.understand(
        "Ho il permesso di soggiorno in rinnovo e devo fare la carta d'identità per la prima volta"
    )["answers"]
    assert permit["motivo"] == "prima" and permit["cittadinanza"] == "extra-ue"


def test_urgent_persona_gets_the_fast_routes_as_a_condition_then_the_questions():
    state, _, reply = demo.start_persona("cie-isola", "en")
    assert state["pending"] == "residenza" and state["urgent_shown"]
    assert "if you are a Milan resident and you can go to the desk in person" in reply["text"]
    # the case keeps the citizen's own answers: the last checklist read is the real one
    last = [s for s in reply["trace"] if s["tool"] == "get_checklist"][-1]
    assert last["input"]["answers"] == state["answers"] and reply["check"]["ok"]


def test_route_links_are_on_their_saved_pages():
    for q in kb.get_service(CIE)["deciding_questions"]:
        for route in (q.get("option_routes") or {}).values():
            for link in route.get("links", []):
                page = (DATA / kb.sources()[link["source_id"]]["snapshot"]).read_text(
                    encoding="utf-8"
                )
                assert link["url"] in page or link["url"] == kb.sources()[link["source_id"]]["url"]
