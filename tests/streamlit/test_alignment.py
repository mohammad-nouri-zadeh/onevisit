"""The demo script, the dossier and the app stay aligned with the live content in data/.

When the content team renames a question or an option, adds a category or a link,
these tests fail instead of the demo silently falling back to a different answer.
"""

from __future__ import annotations

import io
import json
import re

import pytest

from onevisit import agent, demo, dossier, kb, validator

LANGS = ("it", "en", "ar", "es", "zh")
SERVICES = [s["id"] for s in kb.list_services()]


def _choice_questions(service_id: str) -> list[dict]:
    service = kb.get_service(service_id) or {}
    return [
        q for q in service["deciding_questions"] if q.get("options") and q.get("kind") != "date"
    ]


@pytest.mark.parametrize("service_id", SERVICES)
def test_every_live_question_and_option_has_text_in_every_language(service_id):
    script = demo.script()
    for q in _choice_questions(service_id):
        assert q.get("ask_it") and q.get("ask_en"), q["id"]
        for lang in ("ar", "es", "zh"):
            assert script["questions"].get(f"{service_id}.{q['id']}", {}).get(lang), (q["id"], lang)
        for option in q["options"]:
            labels = script["options"].get(option, {})
            assert all(labels.get(lang) for lang in LANGS), (q["id"], option)


def test_script_has_no_labels_for_options_that_no_longer_exist():
    live = {o for sid in SERVICES for q in _choice_questions(sid) for o in q["options"]}
    assert set(demo.script()["options"]) <= live


@pytest.mark.parametrize("persona_id", list(demo.personas()))
def test_persona_answers_are_live_options(persona_id):
    persona = demo.personas()[persona_id]
    questions = {q["id"]: q for q in _choice_questions(persona["service_id"])}
    for qid, value in {**persona.get("inferred", {}), **persona["answers"]}.items():
        if qid in questions:
            assert value in questions[qid]["options"], (qid, value)
    state, _ = demo.play(persona_id, "it")
    # every question the demo asked was answered with the persona's own answer, no fallback
    for qid, value in state["answers"].items():
        assert value == {**persona["answers"], **persona.get("inferred", {})}[qid]


@pytest.mark.parametrize(("persona_id", "minimum"), [("cairo-residenza", 20), ("cie-isola", 15)])
def test_personas_end_with_many_verified_requirements(persona_id, minimum):
    state, turns = demo.play(persona_id, "en")
    reqs = state["checklist"]["requirements"]
    assert len(reqs) >= minimum
    assert all(r["status"] == "verified" for r in reqs)
    final = turns[-1]["text"]
    # the recorded text counts the groups exactly as the live checklist has them
    for category in {r["category"] for r in reqs}:
        n = sum(r["category"] == category for r in reqs)
        assert f"{demo.category_label(category, 'en')} ({n})" in final


def test_residence_demo_says_it_is_submitted_online_with_the_city_form():
    _, turns = demo.play("cairo-residenza", "it")
    online = kb.service_links("iscrizione-anagrafica-extra-ue")["online_form_url"]
    final = turns[-1]["text"]
    assert online["url"] in final and f"[{online['source_id']}]" in final
    assert "prenota" not in validator.fold(final)  # no desk appointment for an online procedure


def test_id_card_demo_books_on_the_page_the_city_links():
    _, turns = demo.play("cie-isola", "it")
    booking = kb.service_links("carta-identita")["booking_url"]
    assert booking["url"] in turns[-1]["text"] and f"[{booking['source_id']}]" in turns[-1]["text"]


def test_booking_link_greeting_names_the_entrance_from_the_city_dataset():
    office = next(o for o in kb.find_offices(limit=1000) if o["id"] == "ds549-01")
    assert office.get("entrance_note")
    _, reply = demo.start_appointment("carta-identita", "ds549-01", "2026-10-20", "en")
    assert office["entrance_note"] in reply["text"] and "20/10/2026" in reply["text"]
    assert reply["check"]["ok"]


@pytest.mark.parametrize("service_id", SERVICES)
def test_every_requirement_has_a_known_category(service_id):
    every = {}
    for q in _choice_questions(service_id):
        every.setdefault(q["id"], q["options"][0])
    for r in kb.checklist(service_id, every)["requirements"]:
        assert r["category"] in kb.CATEGORIES, r["id"]
        assert demo.category_label(r["category"], "ar") != demo.humanize(r["category"])


@pytest.mark.parametrize("service_id", SERVICES)
def test_service_links_are_backed_by_a_saved_source(service_id):
    links = kb.service_links(service_id)
    assert links.get("official_url")
    catalogue = kb.sources()
    for kind, link in links.items():
        row = catalogue[link["source_id"]]
        assert row["url"] == link["url"] or link["url"] in kb._page_text(row), kind
    assert kb.get_service(service_id)["links"] == links
    assert agent.official_page(service_id) == links["official_url"]["url"]


# A first card for a non-EU adult: whether a first-permit receipt is enough is not in the sources.
CIE_OPEN = {
    "motivo": "prima",
    "eta": "adulto",
    "cittadinanza": "extra-ue",
    "residenza": "milano",
    "presenza": "sportello",
}


def test_open_items_say_what_is_unknown_and_where_to_check():
    cl = kb.checklist("carta-identita", CIE_OPEN)
    assert not cl["still_to_ask"]
    assert cl["not_yet_verified"]
    items = kb.open_items("carta-identita", cl["not_yet_verified"])
    assert [i["id"] for i in items] == cl["not_yet_verified"]
    for item in items:
        assert item["text_it"].startswith("Da verificare") and item["url"].startswith("https://")


def test_dossier_groups_by_category_and_prints_the_links_with_their_source():
    pypdf = pytest.importorskip("pypdf")
    answers = {"permesso": "ricevuta-lavoro", "famiglia": "solo", "alloggio": "affitto"}
    pdf = dossier.build_pdf("iscrizione-anagrafica-extra-ue", answers)
    text = re.sub(
        r"\s+", " ", " ".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    )
    reqs = kb.checklist("iscrizione-anagrafica-extra-ue", answers)["requirements"]
    for category in {r["category"] for r in reqs}:
        n = sum(r["category"] == category for r in reqs)
        assert f"{dossier.GROUPS[category][0]} ({n})" in text
    online = kb.service_links("iscrizione-anagrafica-extra-ue")["online_form_url"]
    assert f"[{online['source_id']}]" in text and "MOD_DDR_ESTERO" in text
    assert "Prenotazione / Booking" not in text  # online procedure: no desk booking

    cie = dossier.build_pdf("carta-identita", CIE_OPEN)
    cie_text = re.sub(
        r"\s+", " ", " ".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(cie)).pages)
    )
    assert "Da verificare: le fonti salvate non dicono" in cie_text


def test_online_procedure_is_not_described_as_a_desk_appointment():
    pypdf = pytest.importorskip("pypdf")
    answers = {"permesso": "ricevuta-lavoro", "famiglia": "solo", "alloggio": "affitto"}
    pdf = dossier.build_pdf("iscrizione-anagrafica-extra-ue", answers, appointment="2030-01-15")
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    text = re.sub(r"\s+", " ", " ".join(p.extract_text() for p in reader.pages))
    assert "Dossier per la domanda online" in text and "Planned submission date: 15/01/2030" in text
    assert dossier.FINAL_CHECK_ONLINE[0] in text and dossier.FINAL_CHECK[0] not in text


def test_recorded_city_drafts_name_only_real_sources():
    known = set(kb.sources())
    data = json.loads((demo.DEMO / "drafts.json").read_text(encoding="utf-8"))
    for key, draft in data["drafts"].items():
        assert draft.startswith("BOZZA DA APPROVARE"), key
        for sid in re.findall(r"\bfonte ([a-z0-9][a-z0-9-]+)", draft):
            assert sid in known, (key, sid)
        assert not validator.forbidden_phrases_in(draft), key
