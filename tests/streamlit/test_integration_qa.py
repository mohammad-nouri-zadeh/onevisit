"""The ID card Q&A parts working together: the catalog's new residence answer in the replay's
keyword rules, the search's off-topic gate, quotes cut around the answer, the question-or-case
rules, the official pages' own words ("idonea", "valida") inside verified quotes, and the replay's
measurement on the question bank (data/eval/qa/run_demo_qa.py). No network, no key."""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

from onevisit import demo, kb, search, validator

ROOT = pathlib.Path(__file__).resolve().parents[2]
CIE = "carta-identita"


def _run_demo_qa():
    spec = importlib.util.spec_from_file_location(
        "run_demo_qa", ROOT / "data" / "eval" / "qa" / "run_demo_qa.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------- "altra-regione": resident outside Lombardy, not living in Milan ----------
@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "Ho perso la carta d'identità, sono residente a Torino ma abito a Milano",
            "domicilio-milano",
        ),
        ("Lost my ID card, I am resident in Rome but I live in Isola", "domicilio-milano"),
        ("I lost my ID card; resident in Rome, I don't live in Milan", "altra-regione"),
        (
            "Devo rinnovare la carta d'identità, residente fuori Lombardia e non abito a Milano",
            "altra-regione",
        ),
        ("Ho perso la carta d'identità, sono residente a Padova", None),  # living where? asked
        ("Ho perso la carta d'identità, sono residente a Milano", "milano"),
    ],
)
def test_outside_lombardy_is_read_only_with_where_the_person_lives(text, expected):
    found = demo.understand(text)
    assert found["answers"].get("residenza") == expected
    assert found["area"] != "Padova"  # "residente a Padova" names a town, not via Padova in Milan


def test_resident_elsewhere_not_living_in_milan_is_a_stop_without_booking():
    state, reply = demo.start_text(
        "Ho perso la carta d'identità; sono residente a Roma e non abito a Milano", "it"
    )
    assert state["answers"]["residenza"] == "altra-regione" and state["done"]
    assert demo.case_route(CIE, state["answers"])["kind"] == "stop"
    booking = kb.service_links(CIE).get("booking_url") or {}
    assert reply["check"]["ok"] and (not booking or booking["url"] not in reply["text"])


# ---------- the search's off-topic gate ----------
@pytest.mark.parametrize(
    "text",
    ["Che tempo fa domani?", "What's the weather tomorrow?", "Qual è la capitale della Francia?"],
)
def test_small_talk_never_gets_a_confident_answer(text):
    assert search.best_answer(text, service_id=CIE)["reason"] == "off_topic"
    _, reply = demo.respond(None, text, "it")
    assert reply["qa"]["reason"] != "ok" and reply["qa"]["cards"] == [] and "«" not in reply["text"]
    assert reply["check"]["ok"]


def test_greetings_match_nothing_and_id_card_questions_still_pass_the_gate():
    assert search.best_answer("Come stai?", service_id=CIE)["reason"] == "no_match"
    assert (
        search.best_answer("Qual è il costo della carta d'identità?", service_id=CIE)["reason"]
        == "ok"
    )
    # the weather words don't stop a question that names the card
    out = search.best_answer("Che tempo ci vuole per avere la carta d'identità?", service_id=CIE)
    assert out["reason"] == "ok"


def test_the_police_travel_documents_page_belongs_to_the_id_card():
    found = search.search("Posso prendere il treno mostrando la patente?", service_id=CIE, k=10)
    assert "pds-documenti-viaggio" in {r["source_id"] for r in found}


# ---------- quotes: cut around the answer, widget leftovers dropped, verified ----------
def test_a_long_passage_is_quoted_where_it_answers_and_the_quote_is_verified():
    question = "Posso prenotare insieme gli appuntamenti per tutta la famiglia?"
    state = demo.new_state(None, "it", persona=None, routing="keywords")
    reply = demo.ask(state, question, "it")
    card = next(c for c in reply["qa"]["cards"] if c["source_id"] == "cie")
    assert card["text"].startswith("… ") and "cinque appuntamenti" in card["text"]
    assert reply["check"]["ok"]
    quotes = validator.verify_quotes(
        reply["text"], validator.official_texts_in_trace(reply["trace"]), kb.sources()
    )
    assert quotes and all(q["status"] == "verified" for q in quotes)


def test_focus_quotes_the_opening_when_it_already_answers():
    text = "Il costo è di 22,20 euro. " + "Altre informazioni sul servizio. " * 40
    assert search.focus("Quanto costa?", text, 120)[0] == 0
    assert search.focus("Quanto costa?", "breve", 120) == (0, 5)


def test_the_search_widget_leftovers_are_not_quoted():
    passage = next(p for p in search.passages_for("sedi-anagrafiche") if "Filtri" in p["text"])
    text, _ = demo.excerpt(passage)
    assert "Filtri" not in text and "javascript" not in text


# ---------- the question-or-case rules ----------
@pytest.mark.parametrize(
    "text, kind",
    [
        ("¿Cómo pido cita para la carta de identidad en Milán?", "question"),  # asks about booking
        (
            "Come faccio a vedere a che punto è la lavorazione della mia carta d'identità?",
            "question",
        ),
        ("Come rinnovo la carta d'identità?", "case"),  # the case answers it
        ("Ho perso la carta d'identità, cosa devo fare?", "case"),
        ("ho perso il foglio col puk come lo recupero", "question"),  # a question word inside
        ("buongiorno, mi serve una mano", "unclear"),
    ],
)
def test_how_do_i_questions_that_ask_more_than_the_case_are_questions(text, kind):
    assert demo.classify(None, text) == kind


def test_a_case_opening_with_a_specific_how_question_also_gets_the_passages():
    state, reply = demo.start_text(
        "Ho perso la carta d'identità, come faccio a bloccare la carta?", "it"
    )
    assert state["service_id"] == CIE and state["answers"]["motivo"] == "smarrimento-furto"
    assert reply.get("qa") and reply["qa"]["reason"] == "ok" and reply["check"]["ok"]


# ---------- the official pages' own words inside verified quotes ----------
def test_idonea_in_a_verbatim_quote_is_not_an_eligibility_claim():
    passage = next(
        p for p in search.passages_for("cie-ministero-firma-con-cie") if "idonea" in p["text"]
    )
    texts = [("cie-ministero-firma-con-cie", passage["text"])]
    known = set(kb.sources())
    quoted = (
        "Il Ministero scrive: «idonea a identificare il firmatario» [cie-ministero-firma-con-cie]"
    )
    own = "La tua carta è idonea [cie-ministero-firma-con-cie]"
    args = {"known_ids": known, "read_ids": {"cie-ministero-firma-con-cie"}, "used_facts": []}
    assert validator.check_reply(quoted, official_texts=texts, **args) == []
    assert validator.check_reply(own, official_texts=texts, **args)


# ---------- the replay's measurement ----------
def test_run_demo_qa_scores_what_the_page_shows():
    qa = _run_demo_qa()
    question = {
        "id": "x",
        "answerable": True,
        "expected_sources": ["cie-faq-00305"],
        "evidence": [{"source": "cie-faq-00305", "quote": "è di €22,20 da pagare il giorno"}],
    }

    def reply(reason: str, source: str, text: str) -> dict:
        card = {"source_id": source, "text": text}
        return {"text": f"Lead.\n\n«{text}» [{source}]", "qa": {"reason": reason, "cards": [card]}}

    hit = reply(
        "ok", "cie-faq-00305", "Il costo per il rilascio della CIE è di €22,20 da pagare il giorno"
    )
    assert qa.outcome(question, hit, "question") == "hit"
    assert (
        qa.outcome(
            question,
            reply("ok", "cie-faq-00305", "Altro testo della stessa pagina, lungo abbastanza"),
            "question",
        )
        == "right-page"
    )
    assert (
        qa.outcome(
            question,
            reply("ok", "sedi-anagrafiche", "Orari di apertura degli sportelli"),
            "question",
        )
        == "wrong-confident"
    )
    assert (
        qa.outcome(
            question,
            reply("weak_match", "cie-faq-00305", hit["qa"]["cards"][0]["text"]),
            "question",
        )
        == "closest"
    )
    assert qa.outcome(question, {"text": "Ti aiuto a preparare…"}, "case") == "case"
    unanswerable = {"id": "y", "answerable": False}
    assert qa.outcome(unanswerable, reply("no_match", "cie", "x" * 50), "question") == "honest"
    assert qa.outcome(unanswerable, hit, "question") == "wrong-confident"


def test_run_demo_qa_runs_on_bank_questions_without_a_key():
    qa = _run_demo_qa()
    bank = qa.check_bank.load_bank()["questions"]
    picked = [q for q in bank if q["id"] in ("cie-cost-01", "cie-out-of-scope-01")]
    report = qa.measure(picked)
    assert {r["id"] for r in report["rows"]} == {"cie-cost-01", "cie-out-of-scope-01"}
    for row in report["rows"]:
        assert set(row["modes"]) == set(qa.MODES)
        assert all(m["outcome"] in qa.OUTCOMES and not m["blocked"] for m in row["modes"].values())
    assert "## Answerable questions" in qa.markdown(report, None)


def test_pdf_layout_debris_is_not_quoted_but_lists_and_news_headers_are():
    debris_lines = ("essere riprese con luce", "uniforme e senza ombre,", "né riflessi", "rossi.")
    debris = "\n".join((*debris_lines, "X X", "X X", "X X", "non centrata"))
    assert demo.fragmented(debris)
    office_lines = ("Sedi con cabina", "Delegazione Accursio", "Delegazione Baggio", "Via Larga")
    offices = "\n".join((*office_lines, "Via Oglio", "Viale Padova"))
    news = "Data:\n30 dicembre 2024\nTematiche:\nAnagrafe\nFamiglia\nI giorni di attesa sono scesi."
    assert not demo.fragmented(offices) and not demo.fragmented(news)
    state = demo.new_state(None, "ar", persona=None, routing="keywords")
    reply = demo.ask(state, "هل يمكنني ارتداء الحجاب في صورة بطاقة الهوية الإيطالية؟", "ar")
    assert reply["qa"]["cards"] and not any("X X" in c["text"] for c in reply["qa"]["cards"])


def test_guillemets_of_the_page_become_quote_marks_not_ellipses():
    state = demo.new_state(None, "en", persona=None, routing="keywords")
    reply = demo.ask(state, "I lost my PIN", "en")
    card = next(c for c in reply["qa"]["cards"] if "Sblocca carta" in c["text"])
    assert "“Sblocca carta”" in card["text"] and reply["check"]["ok"]


def test_no_bank_question_gets_a_reply_the_validator_blocks():
    """Every quote the replay shows for the bank questions is found word for word in the passages
    the search returned (the chips' path; the typed path quotes the same passages)."""
    qa = _run_demo_qa()
    blocked = []
    for q in qa.check_bank.load_bank()["questions"]:
        state = demo.new_state(None, "it", persona=None, routing="keywords")
        reply = demo.ask(state, q["question"], "it")
        if not reply["check"]["ok"]:
            blocked.append((q["id"], reply["check"]["blocked"]))
    assert blocked == []
