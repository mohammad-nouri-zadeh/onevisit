"""Guidance that must be right for the case: the tax-code routes, the booked appointment, the lost
card when the person is in a hurry, the via Larga entrance, and items the answers rule out."""

from __future__ import annotations

import json
import pathlib

from onevisit import demo, kb, validator

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
RESIDENCE = "iscrizione-anagrafica-extra-ue"
CAIRO = {"permesso": "ricevuta-lavoro", "famiglia": "solo", "alloggio": "affitto"}


def _snapshot(source_id: str) -> str:
    return (DATA / kb.sources()[source_id]["snapshot"]).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    # the typographic apostrophe of the City's pages, on purpose
    return " ".join(text.replace("’", "'").split()).lower()  # noqa: RUF001


def test_tax_code_step_gives_each_route_under_the_body_that_assigns_it():
    step = next(s for s in kb.get_service(RESIDENCE)["steps"] if s["order"] == 2)
    assert step["ente"] == "questura-milano" and "Questura" in step["text_it"]
    routes = {r["ente"]: r for r in step["routes"]}
    assert set(routes) == {"sportello-unico-immigrazione", "agenzia-entrate"}
    assert "appuntamento" in routes["agenzia-entrate"]["text_it"]
    for item in [step, *step["routes"]]:
        assert item["source_id"] == "codice-fiscale" and item["status"] == "verified"
        assert _norm(item["quote"]) in _norm(_snapshot("codice-fiscale"))
    # the checklist note no longer contradicts the step
    note = next(
        r
        for r in kb.checklist(RESIDENCE, CAIRO)["requirements"]
        if r["id"] == "codice-fiscale-appuntamento"
    )
    assert "Questura" in note["text_it"] and "Sportello Unico" in note["text_it"]


def test_alone_and_renting_hides_the_consent_form_and_moves_the_licence_to_how_it_works():
    reqs = {r["id"]: r for r in kb.checklist(RESIDENCE, CAIRO)["requirements"]}
    assert "consenso-stato-famiglia" not in reqs
    assert reqs["patente"]["category"] == "how"
    guest = {
        r["id"] for r in kb.checklist(RESIDENCE, {**CAIRO, "alloggio": "ospite"})["requirements"]
    }
    assert "consenso-stato-famiglia" in guest


def test_via_larga_entrance_is_confirmed_by_the_id_card_page():
    office = next(o for o in kb.find_offices(limit=100) if o["id"] == "ds549-01")
    assert office["data_issues"] == []
    assert "provvisorio" not in office["entrance_note"].lower()
    conf = office["entrance_confirmed_by"]
    assert conf["source_id"] == "cie" and _norm(conf["quote"]) in _norm(_snapshot("cie"))
    assert any("provvisorio" in n for n in office["dataset_notes"])  # still reported to City staff
    raw = json.loads((DATA / "offices.json").read_text(encoding="utf-8"))
    assert sum(1 for o in raw if o["data_issues"]) == 1


def test_lost_card_and_travelling_opens_with_the_walk_in_exception_and_the_temporary_card():
    state, user_text, reply = demo.start_persona("cie-isola", "it")
    assert "parto" in user_text
    assert state["answers"] == {
        "motivo": "smarrimento-furto",
        "eta": "adulto",
    }  # adult from a first-person message
    # residence comes first; the urgent routes come as a condition (Milan resident, at the desk)
    assert state["urgent"] and state["pending"] == "residenza"
    text = reply["text"]
    usual = {**state["answers"], "residenza": "milano", "presenza": "sportello"}
    reqs = {r["id"]: r for r in kb.checklist("carta-identita", usual)["requirements"]}
    walk_in, temporary = reqs["senza-appuntamento-smarrimento"], reqs["carta-provvisoria"]
    assert "se sei residente a Milano e puoi andare di persona allo sportello" in text
    assert (
        text.index(walk_in["text_it"])
        < text.index(temporary["text_it"])
        < text.index("Una domanda")
    )
    assert f"{temporary['text_it']} [cie]" in text and "via Larga 12" in temporary["text_it"]
    assert reply["check"]["ok"]


def test_urgent_items_are_translated_too():
    _, _, reply = demo.start_persona("cie-isola", "ar")
    assert "Via Larga 12" in reply["text"] and "[cie]" in reply["text"]
    assert any("؀" <= ch <= "ۿ" for ch in reply["text"])


def test_booking_link_marks_the_booking_step_as_done_in_the_dossier():
    import io

    from pypdf import PdfReader

    from onevisit import dossier

    pdf = dossier.build_pdf(
        "carta-identita", {"motivo": "rinnovo"}, office_id="ds549-11", appointment="2030-01-15"
    )
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Appuntamento già prenotato per il 15/01/2030" in text
    assert "Prenota online l'appuntamento" not in text


def test_validator_still_blocks_promises_in_the_new_texts():
    for path in (DATA / "i18n").glob("requirements.*.json"):
        for key, entry in json.loads(path.read_text(encoding="utf-8"))["texts"].items():
            assert not validator.forbidden_phrases_in(entry["text"]), (path.name, key)
