"""Questions about the ID card, answered from the saved official pages: the replay without a key
(onevisit.demo: question detection, extractive answers, the case kept), the app's quote cards,
example-question chips and the cards that follow the case's route. No network, no key."""

from __future__ import annotations

import html
import pathlib
import re

import pytest
from streamlit.testing.v1 import AppTest

from onevisit import demo, kb, search, validator

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = str(ROOT / "app" / "streamlit_app.py")
CIE = "carta-identita"
CIE_PAGE = kb.service_links(CIE)["official_url"]


def _app(**query) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    for k, v in query.items():
        at.query_params[k] = v
    return at.run()


def _markdown(at: AppTest) -> str:
    """The page's Markdown and HTML, entities decoded (&#x27; -> ')."""
    return html.unescape("\n".join(m.value for m in at.markdown))


def _passage(card: dict) -> dict:
    return next(
        p for p in search.passages_for(card["source_id"]) if p["passage_id"] == card["passage_id"]
    )


# ---------- 1. telling a question from an answer and from a new case ----------
QUESTIONS = [
    "Quanto costa la carta d'identità?",
    "quanto costa",
    "Posso fare la foto in Comune",
    "Mio figlio di 2 anni deve venire?",
    "Dove si ritira la carta?",
    "Ma posso andare senza appuntamento?",
    "How much does the ID card cost",
    "Can I pay by card?",
    "Does my 2-year-old have to come to the appointment?",
    "¿Cuánto cuesta el DNI?",
    "cuanto tarda en llegar",
    "Combien coûte la carte d'identité ?",
    "هل يمكنني التقاط الصورة في البلدية؟",
    "كم تكلفة بطاقة الهوية",
    "身份证要多少钱",
    "我两岁的孩子必须到场吗",
    "Ho perso il PIN",  # not worded as a question, short, and a saved page answers it
    "foto in comune",
]


@pytest.mark.parametrize("text", QUESTIONS)
def test_questions_in_many_languages_are_read_as_questions(text):
    assert demo.classify(None, text) == "question"
    state, reply = demo.start_text(text, "it")
    assert reply.get("qa") and reply["routing"] == "search"
    assert state["service_id"] is None and not state["answers"]  # no case was opened


CASES = [
    "Ho perso la carta d'identità e parto il mese prossimo. Abito all'Isola.",
    "La mia carta d'identità è scaduta, sono peruviano",
    "Devo fare la residenza a Milano",
    "I lost my ID card, where do I start?",
    "Devo rinnovare la carta d'identità di mia madre che è allettata",
    "Come rinnovo la carta d'identità?",  # names the procedure and the case: the case answers it
    "buongiorno, mi serve una mano",  # nothing to read: the replay asks which procedure
]


@pytest.mark.parametrize("text", CASES)
def test_case_openings_are_not_questions(text):
    assert demo.classify(None, text) in ("case", "unclear")
    _, reply = demo.start_text(text, "it")
    assert not reply.get("qa") or reply["routing"] != "search"


@pytest.mark.parametrize("persona_id", list(demo.personas()))
@pytest.mark.parametrize("lang", ["it", "en", "ar", "es", "zh"])
def test_persona_openings_start_a_case_and_their_answers_are_answers(persona_id, lang):
    """Every scripted opening (some end with "Da dove comincio?") is a case, and every option the
    replay offers, in every language, is read as an answer to the pending question, never as a
    question for the pages."""
    persona = demo.personas()[persona_id]
    opening = persona["opening"].get(lang) or persona["opening"]["en"]
    assert demo.classify(None, opening) == "case"
    state, _, reply = demo.start_persona(persona_id, lang)
    for _ in range(8):
        if not state.get("pending"):
            break
        for label in reply["options"]:
            assert demo.classify(state, label) == "answer", (state["pending"], label)
        reply = demo.answer(state, reply["options"][0])
        assert not reply.get("qa")


def test_typed_answers_by_keywords_are_answers_not_questions():
    state, _, _ = demo.start_persona("cie-isola", "it")
    demo.answer(state, "Residente a Milano")
    assert state["pending"] == "cittadinanza"
    assert demo.classify(state, "sono peruviano") == "answer"
    assert demo.classify(state, "Extra-UE") == "answer"
    assert demo.classify(state, "3") == "answer"  # the option's number


def test_an_answer_to_another_open_question_is_noted_not_lost():
    state, _ = demo.start_text("Ho perso il PIN della carta d'identità", "it")
    assert state["answers"]["motivo"] == "pin-puk" and state["pending"] == "presenza"
    assert demo.classify(state, "Residente a Milano") == "fact"
    out = demo.answer(state, "Residente a Milano")
    assert state["service_id"] == CIE and state["answers"]["residenza"] == "milano"
    assert state["pending"] == "presenza" and out["check"]["ok"] and not out.get("qa")


def test_question_words_and_marks():
    for text in (
        "Quanto costa?",
        "posso pagare col bancomat",
        "How long",
        "¿Y el precio",
        "Combien ça coûte",
        "هل يجب",
        "多少钱",
        "要带什么吗",
    ):
        assert demo.is_question(text), text
    for text in (
        "Residente a Milano",
        "Sì, viene allo sportello",
        "Devo fare la residenza",
        "I need an ID card",
        "Necesito la carta",
        "Italiana",
        "Adulto",
        "",
    ):
        assert not demo.is_question(text), text


# ---------- 2. the extractive answer ----------
def test_the_answer_quotes_the_passages_verbatim_with_page_publisher_date_and_link():
    _, reply = demo.start_text("Quanto costa la carta d'identità?", "it")
    qa = reply["qa"]
    assert qa["reason"] == "ok" and 1 <= len(qa["cards"]) <= demo.QA_MAX_CARDS
    # one card or more: "Ecco cosa dice la pagina…" / "Ecco cosa dicono le pagine…"
    assert reply["text"].startswith(
        ("Ecco cosa dicono le pagine ufficiali salvate", "Ecco cosa dice la pagina")
    )
    assert "non Claude" in reply["text"].split("\n\n")[0]  # labelled as the replay's keyword search
    assert reply["trace"][0]["tool"] == "search_official_pages"
    assert reply["check"]["ok"] and reply["demo"] is True
    assert qa["cards"][0]["source_id"] == "cie-faq-00305"  # the City's FAQ on the fee
    for card in qa["cards"]:
        passage = _passage(card)
        assert f"«{card['text']}» [{card['source_id']}]" in reply["text"]
        body = validator.normalize_quote(passage["text"])
        for part in card["text"].split("…"):
            if part.strip(" .,;:"):
                assert validator.normalize_quote(part).strip(" .,;:") in body
        assert card["url"].startswith("https://") and card["title"] and card["publisher"]
        assert card["updated_at"] or card["saved_at"]
        assert card["source_id"] in reply["cited"]
    statuses = {
        q["status"]
        for q in validator.verify_quotes(
            reply["text"], validator.official_texts_in_trace(reply["trace"]), kb.sources()
        )
    }
    assert statuses == {"verified"}
    # the official page to check, linked and cited
    assert CIE_PAGE["url"] in reply["text"] and f"[{CIE_PAGE['source_id']}]" in reply["text"]
    assert not reply["options"]  # no case open: nothing to go back to


def test_a_long_passage_is_cut_at_a_sentence_end_and_marked():
    passage = next(
        p for p in search.passages_for("cie-faq-00404") if len(p["text"]) > demo.EXCERPT_CHARS
    )
    text, cut = demo.excerpt(passage)
    assert cut and text.endswith(" …") and len(text) <= demo.EXCERPT_CHARS + 2
    assert not text.startswith("Ho smarrito il PIN")  # the FAQ question is the card's title
    assert "Ultimo aggiornamento" not in text  # the card shows the page's date
    assert text.count("[") == text.count("]")  # never cut inside a link


def test_guillemets_inside_a_page_never_break_the_quote():
    passage = next(p for p in search.passages_for("cie-ministero-faq") if "«" in p["text"])
    text, _ = demo.excerpt(passage, limit=5000)
    assert "«" not in text and "»" not in text
    reply_text = f"«{text}» [cie-ministero-faq]"
    found = validator.verify_quotes(reply_text, [("cie-ministero-faq", passage["text"])])
    assert found[0]["status"] == "verified"


@pytest.mark.parametrize(
    "text, lang, lead",
    [
        ("How much does the ID card cost?", "en", "Here is what the saved official page"),
        ("¿Cuánto tarda en llegar la carta?", "es", "Esto es lo que dice"),
        ("كم تكلفة بطاقة الهوية؟", "ar", "إليك ما تقول"),
        ("身份证要多少钱？", "zh", "以下是已保存的官方页面原文"),  # noqa: RUF001 (Chinese mark on purpose)
        ("Combien coûte la carte d'identité ?", "fr", "Voici ce que di"),
    ],
)
def test_the_lead_follows_the_question_language_and_the_quotes_stay_as_published(text, lang, lead):
    _, reply = demo.start_text(text, "it")
    assert reply["lang"] == lang and reply["text"].startswith(lead)
    assert reply["qa"]["reason"] == "ok" and reply["check"]["ok"]
    for card in reply["qa"]["cards"]:  # the Italian page's own words, not translated
        assert card["text"] in reply["text"]
        assert re.search(r"\b(?:il|la|di|del|della|entro|sono)\b", card["text"]), card["text"]


def test_no_answer_on_the_pages_says_so_and_links_the_official_page(monkeypatch):
    monkeypatch.setattr(
        search,
        "best_answer",
        lambda *a, **k: {
            "query": a[0],
            "confident": False,
            "confidence": 0.0,
            "reason": "no_match",
            "passages": [],
        },
    )
    _, reply = demo.start_text("Posso portare il cane allo sportello?", "it")
    assert reply["qa"]["reason"] == "no_match" and reply["qa"]["cards"] == []
    assert "non rispondono con certezza a questa domanda" in reply["text"]
    assert CIE_PAGE["url"] in reply["text"] and "[cie]" in reply["text"]
    assert "«" not in reply["text"] and reply["check"]["ok"]


def test_a_question_about_another_document_is_not_answered_with_id_card_pages():
    _, reply = demo.start_text("Come rinnovo il passaporto?", "it")
    assert reply["qa"]["reason"] == "other_document" and reply["qa"]["cards"] == []
    assert "un altro documento" in reply["text"] and "non rispondono con certezza" in reply["text"]
    assert reply["check"]["ok"]


def test_a_weak_match_says_so_first_then_shows_the_closest_passages(monkeypatch):
    real = search.best_answer

    def weak(*a, **k):
        out = real(*a, **k)
        return {**out, "reason": "weak_match", "confident": False}

    monkeypatch.setattr(search, "best_answer", weak)
    _, reply = demo.start_text("How much does the ID card cost?", "it")
    parts = reply["text"].split("\n\n")
    assert parts[0].startswith("The saved official pages don't answer this question with certainty")
    assert "may not answer" in reply["text"] and 1 <= len(reply["qa"]["cards"]) <= 2
    assert reply["check"]["ok"]


def test_official_words_in_a_quote_are_not_blocked_but_own_words_are(monkeypatch):
    """A verbatim quote may say "in regola" or "garantito" in the page's own sense; the replay's own
    sentences never do (the validator reads only the words outside verified quotes)."""
    passage = {
        "source_id": "cie-faq-00305",
        "passage_id": "cie-faq-00305#t",
        "title": "Quanto costa",
        "publisher": "Comune di Milano",
        "url": "https://example.invalid/x",
        "saved_at": "2026-10-04",
        "updated_at": "",
        "kind": "faq",
        "lang": "it",
        "heading": "Domanda",
        "text": "Il servizio è garantito in tutte le sedi anagrafiche se il pagamento è in regola "
        "con le tariffe del Comune, come indicato nella pagina.",
        "score": 9.0,
        "confidence": 1.0,
        "confident": True,
    }
    monkeypatch.setattr(
        search,
        "best_answer",
        lambda *a, **k: {
            "query": a[0],
            "confident": True,
            "confidence": 1.0,
            "reason": "ok",
            "passages": [passage],
        },
    )
    _, reply = demo.start_text("Il servizio vale in tutte le sedi?", "it")
    assert validator.forbidden_phrases_in(reply["text"])  # "garantito", "in regola": in the quote
    assert reply["check"]["ok"], reply["check"]


# ---------- 3. questions in the middle of a case ----------
def test_a_question_mid_case_keeps_the_case_and_asks_the_pending_question_again():
    state, _, _ = demo.start_persona("cie-isola", "it")
    demo.answer(state, "Residente a Milano")
    before = {k: state[k] for k in ("service_id", "answers", "pending", "checklist", "offices")}
    before = {**before, "answers": dict(before["answers"])}
    reply = demo.answer(state, "Ma quanto costa?")
    assert reply["qa"]["reason"] == "ok" and reply["qa"]["cards"]
    assert {k: state[k] for k in before} == before  # nothing of the case changed
    assert "Torniamo alla tua pratica." in reply["text"]
    service = kb.get_service(CIE)
    question = next(q for q in service["deciding_questions"] if q["id"] == "cittadinanza")
    assert demo.question_text(CIE, question, "it") in reply["text"]
    assert reply["option_ids"] == question["options"]
    nxt = demo.answer(state, reply["options"][2])  # the case goes on from the same place
    assert state["answers"]["cittadinanza"] == question["options"][2] and nxt["check"]["ok"]


def test_respond_routes_questions_answers_and_new_cases():
    state, reply = demo.respond(None, "Posso fare la foto in Comune?", "it")
    assert reply["qa"] and state["service_id"] is None
    state, reply = demo.respond(state, "Ho perso la carta d'identità, abito in Bovisa", "it")
    assert state["service_id"] == CIE and state["pending"] == "residenza" and not reply.get("qa")
    same = state
    state, reply = demo.respond(state, "quanto ci mette ad arrivare?", "it")
    assert state is same and state["pending"] == "residenza" and reply["qa"]["reason"] == "ok"
    state, reply = demo.respond(state, "Residente a Milano", "it")
    assert state["answers"]["residenza"] == "milano"


def test_a_case_opening_that_also_asks_something_gets_the_passages_first():
    state, reply = demo.start_text("Ho perso la carta d'identità, quanto costa rifarla?", "it")
    assert state["service_id"] == CIE and state["answers"]["motivo"] == "smarrimento-furto"
    # the whole message is searched: what comes before the question stays in it (the card was lost)
    assert reply["qa"]["reason"] == "ok"
    assert reply["qa"]["query"] == "Ho perso la carta d'identità, quanto costa rifarla?"
    assert reply["text"].index("«") < reply["text"].index("Ti aiuto a preparare")
    assert state["pending"] == "residenza" and reply["options"] and reply["check"]["ok"]


def test_after_a_finished_case_the_replay_invites_questions():
    state, _ = demo.play("cie-rinnovo-bovisa", "it")
    assert state["done"]
    out = demo.answer(state, "blah blah")
    assert "domanda" in out["text"] and "non risponde a domande nuove" not in out["text"]
    out = demo.answer(state, "Posso fare la foto in Comune?")
    assert out["qa"]["reason"] == "ok" and state["done"] and not out["options"]


# ---------- 4. example questions ----------
@pytest.mark.parametrize("lang", ["it", "en", "ar", "es", "zh"])
def test_example_questions_exist_in_every_language_and_each_one_is_answered(lang):
    examples = demo.example_questions(lang)
    assert 6 <= len(examples) <= 8
    english = {e["id"]: e for e in demo.example_questions("en")}
    for ex in examples:
        if lang != "en":
            assert ex["label"] != english[ex["id"]]["label"]
            assert ex["query"] != english[ex["id"]]["query"]
        state = demo.new_state(None, lang)
        reply = demo.ask(state, ex["query"], lang)
        assert reply["qa"]["reason"] == "ok", (lang, ex["id"])
        assert reply["check"]["ok"] and reply["qa"]["cards"]
        assert reply["lang"] == lang


def test_french_example_questions_fall_back_to_english():
    assert demo.example_questions("fr") == demo.example_questions("en")


# ---------- 5. the route of the case ----------
MILAN = {"residenza": "milano", "eta": "adulto", "cittadinanza": "italiana"}


@pytest.mark.parametrize(
    "answers, kind, link_ids, booking",
    [
        ({**MILAN, "motivo": "rinnovo", "presenza": "sportello"}, "booking", [], True),
        ({"residenza": "altro-comune-lombardia", "motivo": "prima"}, "stop", [], False),
        (
            {**MILAN, "motivo": "rinnovo", "presenza": "domicilio-salute"},
            "home",
            ["home-form"],
            False,
        ),
        (
            {**MILAN, "motivo": "pin-puk", "presenza": "sportello"},
            "desk",
            ["pin-puk-booking", "contacts-booking"],
            False,
        ),
        (
            {**MILAN, "motivo": "pin-puk", "presenza": "domicilio-salute"},
            "home",
            ["home-form"],
            False,
        ),
        ({**MILAN, "motivo": "gia-cie"}, "info", [], False),
        ({**MILAN, "motivo": "chip", "presenza": "sportello"}, "walk-in", [], False),
    ],
)
def test_case_route_follows_the_answers(answers, kind, link_ids, booking):
    route = demo.case_route(CIE, answers)
    assert route["kind"] == kind and route["booking"] is booking
    assert [link["id"] for link in route["links"]] == link_ids
    assert all(link["source_id"] in kb.sources() for link in route["links"])


def test_not_served_in_milan_names_the_procedure_to_do_first():
    route = demo.case_route(CIE, {"residenza": "altro-comune-lombardia", "motivo": "prima"})
    assert [s["id"] for s in route["services"]] == ["cambio-residenza"]
    page = kb.service_links("cambio-residenza")["official_url"]
    assert route["services"][0]["url"] == page["url"]


def test_online_services_route_to_their_form():
    assert demo.case_route("iscrizione-anagrafica-extra-ue", {})["kind"] == "online"
    assert demo.case_route(None, {})["kind"] == "none"


def _play_app(at: AppTest, labels: list[str]) -> AppTest:
    for label in labels:
        button = next(b for b in at.button if (b.key or "").startswith("opt-") and b.label == label)
        button.click().run()
        assert not at.exception
    return at


def _links(at: AppTest) -> list[tuple[str, str]]:
    return [(b.proto.label, b.proto.url) for b in at.get("link_button")]


def test_app_lost_pin_shows_the_pin_puk_booking_not_the_general_one(no_key, no_network):
    at = _app(demo="1")
    at.chat_input(key="chat_text").set_value(
        "Ho perso il PIN della carta d'identità, abito in Isola"
    ).run()
    at.run()
    _play_app(at, ["Sì, viene allo sportello"])
    assert at.session_state["answers"]["motivo"] == "pin-puk"
    assert not at.session_state["checklist"]["still_to_ask"]
    links = _links(at)
    labels = [label for label, _ in links]
    assert "Prenota il duplicato di PIN e PUK" in labels
    assert "Prenota la modifica dei contatti" in labels
    assert not any("anagrafecie" in url for _, url in links)  # the general CIE booking page
    assert "Prenota sul sito del Comune" not in labels
    assert "Prenota online l'appuntamento" not in _markdown(at)  # step 1 is the PIN/PUK booking


def test_app_home_service_shows_the_home_form_not_the_booking(no_key, no_network):
    at = _app(demo="1")
    at.chat_input(key="chat_text").set_value(
        "Mia madre è costretta a letto e la sua carta d'identità è scaduta"
    ).run()
    at.run()
    _play_app(at, ["Residente a Milano", "Italiana"])
    links = _links(at)
    assert any("SERVIZIO_ANAGRAFICO_DOMICILIO" in url for _, url in links)
    assert not any("anagrafecie" in url for _, url in links)
    assert "Prenota sul sito del Comune" not in [label for label, _ in links]


def test_app_not_served_in_milan_has_no_booking_and_no_desk_steps(no_key, no_network):
    at = _app(demo="1")
    at.chat_input(key="chat_text").set_value(
        "Sono residente a Monza e la mia carta d'identità è scaduta, abito in Isola"
    ).run()
    at.run()
    while any((b.key or "").startswith("opt-") for b in at.button):
        next(b for b in at.button if (b.key or "").startswith("opt-")).click().run()
    assert at.session_state["answers"]["residenza"] == "altro-comune-lombardia"
    links = _links(at)
    assert not any("anagrafecie" in url for _, url in links)
    assert "Prenota sul sito del Comune" not in [label for label, _ in links]
    assert any("cambio-di-residenza" in url for _, url in links)  # what to do first
    text = _markdown(at)
    assert "le voci della checklist dicono perché" in text
    assert "Prenota online l'appuntamento" not in text  # no desk path
    assert "📍" not in text  # and no office to go to
    assert "dossier-pdf-top" not in {d.key for d in at.get("download_button")}  # no desk dossier
    assert not at.date_input  # no appointment date


def test_app_plain_case_still_books_on_the_city_site(no_key, no_network):
    at = _app(demo="1")
    at.button(key="ex-cie-isola").click().run()
    _play_app(at, ["Residente a Milano", "Extra-UE", "Sì, viene allo sportello"])
    labels = [label for label, _ in _links(at)]
    assert "Prenota sul sito del Comune" in labels
    assert "Prenota online l'appuntamento" in _markdown(at)


# ---------- 6. the app ----------
def test_app_example_chip_answers_from_the_pages_in_the_replay(no_key, no_network):
    at = _app(demo="1")
    keys = [b.key for b in at.button if (b.key or "").startswith("qa-ex-")]
    assert len(keys) == len(demo.example_questions("it"))
    at.button(key="qa-ex-cost").click().run()
    assert not at.exception
    user, reply = at.session_state["chat"][-2:]
    assert user["role"] == "user" and user["text"] == "Quanto costa la carta d'identità?"
    assert reply["routing"] == "search" and reply["qa"]["reason"] == "ok"
    text = _markdown(at)
    assert text.count('class="ov-q"') == len(reply["qa"]["cards"])
    assert "€22,20" in text and "testo identico alla pagina salvata" in text
    assert "pagina aggiornata il" in text  # the page's own date
    assert "passaggi scelti per parole chiave" in text  # labelled: not Claude
    assert "La ricerca per parole chiave ha trovato" in text
    assert "OneVisit · Claude" not in text
    trace = next(e for e in at.expander if e.label == "Cosa hanno controllato gli strumenti")
    assert "nelle pagine ufficiali salvate" in "\n".join(m.value for m in trace.markdown)


def test_app_question_typed_mid_case_keeps_the_case(no_key, no_network):
    at = _app(demo="1")
    at.button(key="ex-cie-isola").click().run()
    _play_app(at, ["Residente a Milano"])
    answers = dict(at.session_state["demo_state"]["answers"])
    at.chat_input(key="chat_text").set_value("Posso fare la foto in Comune?").run()
    at.run()
    assert not at.exception
    assert at.session_state["demo_state"]["answers"] == answers
    assert at.session_state["demo_state"]["pending"] == "cittadinanza"
    assert at.session_state["chat"][-1]["qa"]["reason"] == "ok"
    assert at.session_state["checklist"]["requirements"]  # the checklist is still on the page
    options = [b.label for b in at.button if (b.key or "").startswith("opt-")]
    assert options == ["Italiana", "UE", "Extra-UE"]  # the pending question, one tap away
    _play_app(at, ["Extra-UE"])
    assert at.session_state["demo_state"]["answers"]["cittadinanza"] == "extra-ue"


@pytest.mark.parametrize(
    "lang, label",
    [
        ("en", "How much does it cost?"),
        ("ar", "كم التكلفة؟"),
        ("es", "¿Cuánto cuesta?"),
        ("zh", "要多少钱？"),  # noqa: RUF001 (Chinese mark on purpose)
    ],
)
def test_app_example_chips_follow_the_page_language(no_key, no_network, lang, label):
    at = _app(demo="1", lang=lang)
    assert at.button(key="qa-ex-cost").label == label
    at.button(key="qa-ex-cost").click().run()
    assert not at.exception and at.session_state["chat"][-1]["lang"] == lang


def test_live_reply_quotes_render_as_cards_and_the_search_in_the_trace(monkeypatch, no_network):
    """With a key, Claude (a fake here) searches the pages and quotes a passage: the app shows the
    quote as a card linked to its source, and the search in "What Claude checked"."""
    import anthropic
    from fakes import FakeClient, text, tool

    top = search.best_answer("Quanto costa la carta d'identità?", service_id=CIE)["passages"][0]
    sentence = next(s for s in top["text"].split("\n") if "€" in s).strip()
    fake = FakeClient(
        [
            tool(
                "search_official_pages", query="Quanto costa la carta d'identità?", service_id=CIE
            ),
            text(f"La pagina dice: «{sentence}» [{top['source_id']}]. Si paga allo sportello."),
        ]
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-" + "x" * 40)
    at = _app()
    at.button(key="qa-ex-cost").click().run()
    assert not at.exception
    reply = at.session_state["chat"][-1]
    assert reply["check"]["ok"] and not reply.get("demo")
    md = _markdown(at)
    assert md.count('class="ov-q"') == 1 and f'data-source="{top["source_id"]}"' in md
    assert "testo identico alla pagina salvata" in md and "Claude ha letto" in md
    assert "<p>Si paga allo sportello.</p>" in md  # the sentence after the card, without the dot
    trace = next(e for e in at.expander if e.label == "Cosa ha controllato Claude")
    assert "nelle pagine ufficiali salvate" in "\n".join(m.value for m in trace.markdown)
