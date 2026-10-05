"""Regressions from the review of the ID card Q&A (2026-10-05): the search's gates and confidence,
the replay's reading of a message, and the cards it shows. No network, no key."""

from __future__ import annotations

import json

import pytest

from onevisit import demo, search, tools

CIE = "carta-identita"


def _best(q: str) -> dict:
    return search.best_answer(q, CIE, k=5)


# ---------- the search ----------
def test_circular_letterheads_are_not_indexed():
    for sid in ("circ-dait-060-2026", "circ-dait-054-2026", "circ-dait-081-2023"):
        first = search.passages_for(sid)[0]["text"]
        assert first.lstrip("*").startswith("OGGETTO"), (sid, first[:80])
    found = search.search(
        "my card was stolen yesterday, can i still travel to rome by train?", CIE, k=5
    )
    assert not any("PREFETTI" in r["text"] or "LORO SEDI" in r["text"] for r in found)


def test_travel_in_italy_finds_the_documents_for_travelling_at_home():
    found = _best("my card was stolen yesterday, can i still travel to rome by train?")
    top = {r["source_id"] for r in found["passages"][:3]}
    assert top & {
        "pds-documenti-viaggio",
        "cie-faq-00355",
        "cie-faq-04355",
        "cie-ministero-viaggiare",
    }


@pytest.mark.parametrize(
    "question",
    [
        "Can my friend book the appointment for me using his SPID?",
        "posso prenotare per tutta la famiglia con un solo spid?",
    ],
)
def test_spid_as_the_means_of_booking_is_about_the_card(question):
    found = _best(question)
    assert found["reason"] == "ok"
    assert {r["source_id"] for r in found["passages"][:2]} & {"cie", "cie-faq-00578"}


def test_getting_spid_or_a_passport_is_another_document():
    assert _best("How do I get SPID?")["reason"] == "other_document"
    # asking to obtain a passport at the anagrafe, even next to the ID card
    assert (
        _best("Posso fare il passaporto all'anagrafe insieme alla carta d'identità?")["reason"]
        == "other_document"
    )
    assert (
        _best("Devo portare il passaporto per la carta d'identità?")["reason"] != "other_document"
    )


@pytest.mark.parametrize(
    "question",
    [
        "Come va fatta la foto?",
        "Come va presentata la denuncia di smarrimento?",
        "How are you supposed to pay?",
        "Che documenti servono se piove?",
        "come va compilato il modulo per il domicilio",
        "La ricetta medica serve per il servizio a domicilio?",
    ],
)
def test_ordinary_words_are_not_small_talk(question):
    assert _best(question)["reason"] != "off_topic"


@pytest.mark.parametrize("question", ["Come va?", "Che tempo fa domani?", "How are you?"])
def test_small_talk_is_still_off_topic(question):
    found = _best(question)  # "How are you?" has no word a page has: nothing matches at all
    assert found["reason"] in ("off_topic", "no_match") and not found["confident"]


@pytest.mark.parametrize(
    "question",
    [
        "C'è un parcheggio vicino alla sede di via Larga?",
        "Can I bring my dog to the anagrafe?",
        "Я маю тимчасовий захист в Італії. Чи можу я отримати ID-картку?",
    ],
)
def test_topics_no_page_answers_get_no_confident_passage(question):
    found = _best(question)
    assert found["reason"] == "unknown_words" and not found["confident"]


def test_a_passage_must_hold_what_is_asked_not_only_the_situation():
    # "free for people over 70": a passage on the over-70s' validity alone is not the answer
    found = _best("Is it true the ID card is free for people over 70?")
    for r in found["passages"]:
        if r["confident"]:
            assert "§cost" in search.held_concepts(found["query"], r["passage_id"]), r["passage_id"]
    # the situation ("if I lost it") is context: the fee answers
    lost = _best("quanto costa la carta d'identità se l'ho persa?")
    assert lost["reason"] == "ok" and lost["passages"][0]["source_id"] == "cie-faq-00305"


def test_a_section_about_another_thing_is_never_confident():
    found = _best("¿Puedo usar la carta de identidad para viajar a Turquía?")
    for r in found["passages"]:
        if search.heading_mismatch(found["query"], r["passage_id"]):
            assert not r["confident"], r["heading"]


def test_headings_with_link_titles_and_split_headings_read_whole():
    headings = [p["heading"] for p in search.passages_for("sedi-anagrafiche")]
    assert "Sedi anagrafiche > Via Larga" in headings
    assert not any("javascript" in h or '")' in h for h in headings)
    yes = [p["heading"] for p in search.passages_for("yesmilano-id-card")]
    assert any(h.endswith("City Registry office and delivery of the card") for h in yes)
    assert not any(h.split(" > ")[-1] == "and delivery of the card" for h in yes)


@pytest.mark.parametrize("service_id", ["cie", 123, ["x"], "../..", "CIE"])
def test_an_unknown_service_id_falls_back_to_the_conversation_service(service_id):
    out = json.loads(
        tools.run_tool(
            "search_official_pages",
            {"query": "quanto costa la carta", "service_id": service_id},
            service_id=CIE,
        )
    )
    assert out["reason"] == "ok" and out["results"] and out["official_page"]["source_id"] == "cie"
    assert "Unknown service_id" in out["service_note"] and "error" not in out


def test_the_search_tool_does_not_echo_or_keep_the_persons_words():
    concepts = search._concepts(search._stat(search.SYNONYMS_FILE))
    before = set(concepts._first_cache)
    out = json.loads(
        search.run_tool(
            {
                "query": "mi chiamo Zorbaxqu Plinthwick, via Lupetta: quanto costa?",
                "service_id": CIE,
            }
        )
    )
    assert "query" not in out
    assert not {"zorbaxqu", "plinthwick", "lupetta"} & (set(concepts._first_cache) - before)


def test_a_pasted_page_is_cut_and_searched_in_a_few_parts():
    long = "Quanto costa la carta? " * 2000
    out = json.loads(search.run_tool({"query": long, "service_id": CIE}))
    assert out["results"] and len(search._parts(long[: search.MAX_QUERY_CHARS])) >= 1


# ---------- the replay's reading of a message ----------
@pytest.mark.parametrize(
    "text",
    [
        "Ho perso la tessera sanitaria, posso fare lo stesso la carta d'identità?",
        "Mi pasaporte está vencido, ¿puedo sacar la carta de identidad igual?",
        "sono in regola per fare la carta d'identità se ho il permesso scaduto da 2 mesi?",
    ],
)
def test_another_documents_loss_or_expiry_is_not_the_cards(text):
    assert "motivo" not in demo.understand(text)["answers"]


@pytest.mark.parametrize(
    ("text", "motivo"),
    [
        ("Mi hanno rubato il portafoglio con la carta d'identità", "smarrimento-furto"),
        ("Ho perso il portafoglio con bancomat e carta d'identità", "smarrimento-furto"),
        ("La mia carta è scaduta", "rinnovo"),
    ],
)
def test_the_cards_own_loss_or_expiry_is_still_read(text, motivo):
    assert demo.understand(text)["answers"].get("motivo") == motivo


@pytest.mark.parametrize(
    "text",
    [
        "qnt tempo ci vuole x avere la cie dopo l appuntamento",
        "wat hapens if i miss my apointment for the id card",
        "ho perso il foglio col puk come lo recupero",
    ],
)
def test_shorthand_and_inner_question_words_are_questions(text):
    assert demo.classify(None, text) == "question"


def test_a_comparison_or_a_time_is_not_a_question():
    assert not demo.is_question("Sono residente a Milano come mia moglie")
    assert not demo.is_question("Ho perso la carta d'identità quando ero a Roma")


def test_a_question_about_another_procedure_keeps_the_case_and_offers_a_new_one():
    state, _, _ = demo.start_persona("cairo-residenza", "it")
    pending = state["pending"]
    state, reply = demo.respond(state, "quanto costa la carta d'identità se l'ho persa?", "it")
    assert state["service_id"] == "iscrizione-anagrafica-extra-ue" and state["pending"] == pending
    assert reply["qa"]["cards"] and reply["option_ids"][-1] == demo.NEW_CASE
    assert "resta aperta" in reply["text"] and reply["check"]["ok"]
    state, reply = demo.respond(state, reply["options"][-1], "it")  # the "new case" button
    assert state["service_id"] == CIE and state["answers"]["motivo"] == "smarrimento-furto"
    assert reply["text"].startswith("Ho chiuso la pratica precedente") and reply["check"]["ok"]


def test_a_new_case_typed_mid_case_says_the_earlier_one_was_closed():
    state, _, _ = demo.start_persona("cairo-residenza", "it")
    state, reply = demo.respond(state, "Ho perso la carta d'identità", "it")
    assert state["service_id"] == CIE and reply["text"].startswith(
        "Ho chiuso la pratica precedente"
    )


def test_an_answer_with_a_question_is_both():
    state, _, _ = demo.start_persona("cie-rinnovo-bovisa", "it")
    assert state["pending"] == "residenza"
    state, reply = demo.respond(state, "Residente a Milano, e quanto costa?", "it")
    assert state["answers"]["residenza"] == "milano"
    assert reply["qa"]["reason"] == "ok" and reply["qa"]["cards"][0]["source_id"] == "cie-faq-00305"
    assert reply["check"]["ok"]


def test_a_question_inside_a_case_opening_is_never_dropped():
    state, reply = demo.start_text(
        "Ma fille de 12 ans peut-elle prendre l'avion seule pour Paris avec sa carte d'identité ?",
        "it",
    )
    assert state["service_id"] == CIE and reply.get("qa")
    assert (
        reply["qa"]["reason"] != "ok" and "[cie]" in reply["text"]
    )  # the honest line with the official page
    assert reply["text"].index("[cie]") < reply["text"].index("Electronic identity card")


def test_offices_by_neighbourhood_and_the_nearest_office():
    state, _, _ = demo.start_persona("cie-isola", "it")
    state, reply = demo.respond(state, "C'è la cabina foto a Isola?", "it")
    assert "Largo De Benedetti 1" in reply["text"] and "[ds549]" in reply["text"]
    assert reply["qa"]["cards"][0]["source_id"] == "cie-cabine-foto"
    state, reply = demo.respond(state, "¿Y dónde está la oficina más cercana a Lambrate?", "it")
    assert "[sedi-anagrafiche]" in reply["text"] and reply["check"]["ok"]


def test_anagrafe_alone_keeps_the_id_card_pages():
    found = demo.understand(
        "Mia nonna ha 85 anni ma cammina, deve per forza venire di persona in anagrafe?"
    )
    assert demo.qa_service(None, found, "deve per forza venire di persona in anagrafe?") == CIE


# ---------- the cards ----------
def test_a_short_passage_is_quoted_whole():
    _, reply = demo.start_text("Il chip non funziona più, devo pagare di nuovo 22 euro?", "it")
    assert any("a costo zero" in c["text"] for c in reply["qa"]["cards"])


def test_the_citys_page_comes_before_a_guide_for_newcomers():
    _, reply = demo.start_text(
        "Can I get my ID card delivered to my university dorm instead of my home?", "it"
    )
    cards = reply["qa"]["cards"]
    assert cards[0]["source_id"] == "cie-faq-00577"
    assert not any("ten working days" in c["text"] for c in cards)


def test_the_citys_fee_is_not_shown_with_the_ministrys_share():
    _, reply = demo.start_text("Quanto costa la carta d'identità?", "it")
    assert reply["qa"]["cards"][0]["source_id"] == "cie-faq-00305"
    assert not any("16,79" in c["text"] for c in reply["qa"]["cards"])
    assert not any("identità digitale" in c["text"] for c in reply["qa"]["cards"])


def test_the_reply_language_follows_the_question_and_back():
    state, _, _ = demo.start_persona("cie-isola", "it")
    state, reply = demo.respond(state, "wait, does my 5 year old need to come too?", "it")
    assert reply["lang"] == "en" and state["lang"] == "en"
    assert reply["qa"]["cards"][0]["source_id"] in ("cie-faq-00412", "cie")
    state, reply = demo.respond(state, "C'è la cabina foto a Isola?", "en")
    assert reply["lang"] == "it" and state["lang"] == "it"


def test_the_page_follows_the_language_the_replay_answers_in(no_key, no_network):
    """One detector: after a reply, the page (buttons, labels) is in the reply's language."""
    import pathlib

    from streamlit.testing.v1 import AppTest

    app = str(pathlib.Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py")
    at = AppTest.from_file(app, default_timeout=60)
    at.query_params["demo"] = "1"
    at.run()
    at.chat_input[0].set_value("Ho perso la carta d'identità, abito all'Isola").run()
    assert at.session_state["lang"] == "it"
    at.chat_input[0].set_value("wait, does my 5 year old need to come too?").run()
    at.run()  # the language switch applies on the next run
    assert at.session_state["chat"][-1]["lang"] == "en" and at.session_state["lang"] == "en"
    at.chat_input[0].set_value("C'è la cabina foto a Isola?").run()
    at.run()
    assert at.session_state["chat"][-1]["lang"] == "it" and at.session_state["lang"] == "it"
    assert not at.exception


# ---------- the checklist: stop routes and answer values ----------
def test_a_stop_route_holds_only_while_the_card_could_still_be_issued():
    """Resident in another region: the card is not issued in Milan, but a PIN/PUK duplicate is
    requested at any registry desk, so that case keeps its desk route and its question."""
    pin = json.loads(
        tools.run_tool(
            "get_checklist",
            {"service_id": CIE, "answers": {"residenza": "altra-regione", "motivo": "pin-puk"}},
        )
    )
    assert pin["still_to_ask"] == ["presenza"]
    assert [(r["question"], r["route"]) for r in pin["routes"]] == [("motivo", "desk")]
    first = json.loads(
        tools.run_tool(
            "get_checklist",
            {"service_id": CIE, "answers": {"residenza": "altra-regione", "motivo": "prima"}},
        )
    )
    assert first["still_to_ask"] == []
    assert [(r["question"], r["route"]) for r in first["routes"]] == [("residenza", "stop")]


def test_an_answer_that_is_not_an_option_is_ignored_and_named():
    out = json.loads(
        tools.run_tool(
            "get_checklist",
            {"service_id": CIE, "answers": {"residenza": "Milano", "eta": "adult"}},
        )
    )
    assert {a["question"] for a in out["invalid_answers"]} == {"residenza", "eta"}
    assert "residenza" in out["still_to_ask"] and "eta" in out["still_to_ask"]
