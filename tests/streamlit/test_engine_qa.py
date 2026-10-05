"""The engine answers any ID card question from the saved official pages (fake clients only).

Claude searches (search_official_pages, read_source), quotes the decisive sentence verbatim
between « » with its [source_id], or says the saved pages don't answer and links the official
page. The validator checks every quote against the passages the tools returned; the question
flow asks only what still changes the answer and follows the routes. Never the network.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fakes import FakeClient, text, tool

from onevisit import agent, evaluate, kb, search, tools, validator

ROOT = pathlib.Path(__file__).resolve().parents[2]
CIE = "carta-identita"
CIE_PAGE = "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita"
PASSAGE_FIELDS = {
    "source_id",
    "passage_id",
    "title",
    "publisher",
    "url",
    "saved_at",
    "updated_at",
    "kind",
    "lang",
    "heading",
    "text",
    "score",
    "confidence",
    "confident",
}


def _top(query: str) -> dict:
    """The passage the search tool will return first for this query (same input, same output)."""
    return search.search(query, service_id=CIE, k=5)[0]


def _sentence(passage: dict) -> str:
    return evaluate._first_sentence(passage["text"])


# ---------------------------------------------------------------- tools: the contract shape


def test_the_two_question_tools_follow_the_contract():
    by_name = {t["name"]: t for t in tools.TOOLS}
    search_tool = by_name["search_official_pages"]["input_schema"]
    assert set(search_tool["properties"]) == {"query", "service_id"}
    assert search_tool["required"] == ["query"]
    read_tool = by_name["read_source"]["input_schema"]
    assert set(read_tool["properties"]) == {"source_id"} and read_tool["required"] == ["source_id"]


def test_search_tool_returns_passages_and_uses_the_conversation_service():
    query = "Quanto costa la carta d'identità elettronica?"
    payload = json.loads(tools.run_tool("search_official_pages", {"query": query}, service_id=CIE))
    explicit = json.loads(search.run_tool({"query": query, "service_id": CIE}))
    assert payload == explicit  # the default service is the one the conversation is about
    assert payload["results"] and all(set(r) >= PASSAGE_FIELDS for r in payload["results"])
    assert payload["official_page"] == {
        "url": CIE_PAGE,
        "source_id": "cie",
        "title": kb.get_source("cie")["title"],
    }
    # the input's own service wins over the conversation's
    other = json.loads(
        tools.run_tool(
            "search_official_pages",
            {"query": query, "service_id": "cambio-residenza"},
            service_id=CIE,
        )
    )
    assert other["official_page"]["source_id"] != "cie"
    nothing = json.loads(tools.run_tool("search_official_pages", {"query": "xqzv blorpt"}))
    assert nothing["results"] == [] and "note" in nothing and "official_page" not in nothing


def test_read_source_gives_the_saved_page_verbatim_and_capped():
    out = json.loads(tools.run_tool("read_source", {"source_id": "cie"}))
    assert set(out) >= {
        "source_id",
        "title",
        "publisher",
        "url",
        "updated_at",
        "saved_at",
        "passages",
        "truncated",
    }
    assert out["source_id"] == "cie" and out["url"] == CIE_PAGE
    page = (ROOT / "data" / "pages" / "cie.md").read_text(encoding="utf-8")
    for p in out["passages"]:
        assert set(p) == {"passage_id", "heading", "text"} and p["text"] in page
    assert sum(len(p["text"]) for p in out["passages"]) <= tools.READ_SOURCE_MAX_CHARS
    assert out["truncated"] == (len(out["passages"]) < len(search.passages_for("cie")))
    small = tools.read_source("cie", max_chars=10)
    assert len(small["passages"]) == 1 and small["truncated"]  # the first passage always comes
    no_page = tools.read_source("ds549")  # an open dataset: nothing to quote
    assert no_page["passages"] == [] and no_page["note"]
    assert "error" in json.loads(tools.run_tool("read_source", {"source_id": "nope"}))


def test_checklist_tool_exposes_the_routes_with_their_links():
    out = json.loads(
        tools.run_tool("get_checklist", {"service_id": CIE, "answers": {"motivo": "pin-puk"}})
    )
    [route] = [r for r in out["routes"] if r["question"] == "motivo"]
    assert route["route"] == "desk" and not route["ends_case"]
    assert any("richiesta-duplicato-pin-puk" in link["url"] for link in route["links"])
    assert {link["source_id"] for link in route["links"]} <= validator.sources_in(out)
    home = kb.checklist(
        CIE, {"residenza": "milano", "motivo": "rinnovo", "presenza": "domicilio-salute"}
    )
    assert any(
        "SERVIZIO_ANAGRAFICO_DOMICILIO" in link["url"]
        for r in home["routes"]
        for link in r.get("links", [])
    )
    monza = kb.checklist(CIE, {"residenza": "altro-comune-lombardia", "motivo": "rinnovo"})
    [stop] = [r for r in monza["routes"] if r["ends_case"]]
    assert all(s["official_url"]["source_id"] in kb.sources() for s in stop["services"])
    assert {s["official_url"]["source_id"] for s in stop["services"]} <= validator.sources_in(monza)


# ---------------------------------------------------------------- kb: which question next


def _verified(rid: str, when: dict) -> dict:
    return {
        "id": rid,
        "text_it": rid,
        "when": when,
        "source_id": "cie",
        "quote": "q",
        "status": "verified",
        "category": "how",
    }


SYNTHETIC = {
    "id": "finto",
    "title": {"it": "Finto", "en": "Fake"},
    "deciding_questions": [
        {
            "id": "residenza",
            "ask_it": "?",
            "options": ["qui", "fuori"],
            "option_routes": {
                "fuori": {
                    "route": "stop",
                    "services": [{"id": "altro", "when": {"cittadinanza": ["extra-ue"]}}],
                }
            },
        },
        {
            "id": "motivo",
            "ask_it": "?",
            "options": ["rinnovo", "pin"],
            "option_routes": {
                "pin": {
                    "route": "desk",
                    "links": [{"id": "pin", "url": "https://example.org/pin", "source_id": "cie"}],
                }
            },
        },
        {"id": "eta", "ask_it": "?", "options": ["adulto", "minore"]},
        {"id": "cittadinanza", "ask_it": "?", "options": ["italiana", "extra-ue"]},
    ],
    "requirements": [
        _verified("foto", {"residenza": ["qui"], "motivo": ["rinnovo"]}),
        _verified("minori", {"residenza": ["qui"], "motivo": ["rinnovo"], "eta": ["minore"]}),
        _verified(
            "stranieri", {"residenza": ["qui"], "motivo": ["rinnovo"], "cittadinanza": ["extra-ue"]}
        ),
        _verified("pin", {"motivo": ["pin"]}),
        _verified("solo-residenti", {"residenza": ["fuori"], "motivo": ["rinnovo"]}),
    ],
}
OTHER = {
    "id": "altro",
    "title": {"it": "Altro", "en": "Other"},
    "deciding_questions": [],
    "requirements": [],
}


@pytest.fixture
def synthetic(monkeypatch):
    monkeypatch.setattr(kb, "_services", lambda: {"finto": SYNTHETIC, "altro": OTHER})
    return "finto"


def test_questions_come_in_the_catalog_order_not_alphabetically(synthetic):
    assert kb.checklist(synthetic, {})["still_to_ask"] == [
        "residenza",
        "motivo",
        "eta",
        "cittadinanza",
    ]
    assert kb.questions_to_ask(synthetic, {}) == kb.checklist(synthetic, {})["still_to_ask"]
    assert kb.questions_to_ask("nope", {}) == []


def test_a_question_nothing_possible_depends_on_is_not_asked(synthetic):
    # a lost PIN: no item of that path depends on age, citizenship or residence
    pin = kb.checklist(synthetic, {"motivo": "pin"})
    assert pin["still_to_ask"] == [] and [r["id"] for r in pin["requirements"]] == ["pin"]
    [route] = pin["routes"]
    assert route == {
        "question": "motivo",
        "answer": "pin",
        "route": "desk",
        "ends_case": False,
        "links": [{"id": "pin", "url": "https://example.org/pin", "source_id": "cie"}],
    }
    renewal = kb.checklist(synthetic, {"residenza": "qui", "motivo": "rinnovo"})
    assert renewal["still_to_ask"] == ["eta", "cittadinanza"] and renewal["routes"] == []


def test_a_stop_route_ends_the_case_except_for_its_own_questions(synthetic):
    away = kb.checklist(synthetic, {"residenza": "fuori"})
    # its items depend on motivo; the service it points to depends on citizenship; age: nothing
    assert away["still_to_ask"] == ["motivo", "cittadinanza"]
    [stop] = away["routes"]
    assert stop["ends_case"] and "services" not in stop
    done = kb.checklist(
        synthetic, {"residenza": "fuori", "motivo": "rinnovo", "cittadinanza": "extra-ue"}
    )
    assert done["still_to_ask"] == [] and done["routes"][0]["services"][0]["id"] == "altro"
    assert [r["id"] for r in done["requirements"]] == ["solo-residenti"]


def _oracle(answers: dict) -> list[str]:
    """An independent reading of the real catalog: the questions that a requirement no answer
    rules out yet depends on (only the stop's own items once a stop route is chosen, plus the
    services it points to), in the catalog's order."""
    svc = kb._services()[CIE]
    stops = [
        (q["id"], route)
        for q in svc["deciding_questions"]
        if (route := (q.get("option_routes") or {}).get(answers.get(q["id"])))
        and route.get("route") == "stop"
    ]
    whens = [r.get("when") or {} for r in svc["requirements"]]
    if stops:
        whens = [w for w in whens if any(qid in w for qid, _ in stops)]
        whens += [s.get("when") or {} for _, route in stops for s in route.get("services", [])]
    needed = set()
    for when in whens:
        if all(answers[q] in allowed for q, allowed in when.items() if q in answers):
            needed |= {q for q in when if q not in answers}
    return [q["id"] for q in svc["deciding_questions"] if q["id"] in needed]


@pytest.mark.parametrize(
    "answers",
    [
        {},
        {"motivo": "pin-puk"},  # lost PIN/PUK
        {"motivo": "pin-puk", "presenza": "domicilio-salute"},
        {"motivo": "gia-cie"},  # already has the card, a question about it
        {"residenza": "milano", "motivo": "rinnovo", "presenza": "domicilio-salute"},  # home
        {"residenza": "milano", "motivo": "prima", "eta": "minore"},  # a minor
        {"residenza": "altro-comune-lombardia", "motivo": "rinnovo"},  # not served in Milan
        {"residenza": "non-residente"},
        {"motivo": "smarrimento-furto", "eta": "adulto"},
    ],
)
def test_real_id_card_questions_follow_the_data(answers):
    cl = kb.checklist(CIE, answers)
    assert cl["still_to_ask"] == _oracle(answers)
    assert not set(cl["still_to_ask"]) & set(answers)


def test_real_id_card_routes():
    pin = kb.checklist(CIE, {"motivo": "pin-puk"})
    assert any(
        "richiesta-duplicato-pin-puk" in link["url"]
        for r in pin["routes"]
        for link in r.get("links", [])
    )
    monza = kb.checklist(CIE, {"residenza": "altro-comune-lombardia", "motivo": "rinnovo"})
    [stop] = [r for r in monza["routes"] if r["question"] == "residenza"]
    assert stop["ends_case"] and "cambio-residenza" in [s["id"] for s in stop["services"]]
    assert "eta" not in monza["still_to_ask"] and "presenza" not in monza["still_to_ask"]
    minor = {
        "residenza": "milano",
        "motivo": "prima",
        "eta": "minore",
        "cittadinanza": "italiana",
        "presenza": "sportello",
    }
    assert kb.checklist(CIE, minor)["still_to_ask"] == []


# ---------------------------------------------------------------- the agent with a fake Claude


def test_search_then_a_verbatim_quote_passes():
    query = "Posso prenotare anche per mia moglie e i miei figli?"
    top = _top(query)
    answer = (
        f"Sì, con SPID o CIE: «{_sentence(top)}» [{top['source_id']}]. "
        "La verifica finale spetta all'operatore allo sportello."
    )
    client = FakeClient([tool("search_official_pages", query=query, service_id=CIE), text(answer)])
    messages = [{"role": "user", "content": query}]
    reply = agent.run_turn(messages, client=client, lang="it")
    assert reply["check"] == {"attempts": 1, "blocked": [], "fallback": False, "ok": True}
    assert reply["qa"] and reply["cited"] == [top["source_id"]]
    assert reply["quotes"] == [
        {"text": _sentence(top), "source_id": top["source_id"], "url": top["url"], "exact": True}
    ]
    assert reply["trace"][0]["tool"] == "search_official_pages"


def test_read_source_passages_count_for_quotes_and_citations():
    page = tools.read_source("cie-faq-03614")
    line = next(p["text"] for p in page["passages"] if "in regola" in p["text"])
    quote = "redatta in lingua italiana o in regola con le norme sulla traduzione"
    assert quote in " ".join(line.split())
    client = FakeClient(
        [
            tool("read_source", source_id="cie-faq-03614"),
            text(f"La pagina chiede un'attestazione del Consolato «{quote}» [cie-faq-03614]."),
        ]
    )
    reply = agent.run_turn([{"role": "user", "content": "Che documento del consolato?"}], client)
    # "in regola" is the page's own wording, inside a verified quote: not an eligibility claim
    assert reply["check"]["ok"], reply["check"]
    assert reply["quotes"][0]["source_id"] == "cie-faq-03614"


def test_an_eligibility_word_outside_the_quote_is_blocked():
    quote = "redatta in lingua italiana o in regola con le norme sulla traduzione"
    client = FakeClient(
        [
            tool("read_source", source_id="cie-faq-03614"),
            text(f"Sei in regola: «{quote}» [cie-faq-03614]."),
            text(f"Il Consolato rilascia un'attestazione «{quote}» [cie-faq-03614]."),
        ]
    )
    reply = agent.run_turn([{"role": "user", "content": "Sono in regola?"}], client=client)
    assert reply["check"]["blocked"] == ["eligibility_claim:in regola"]
    assert reply["check"]["attempts"] == 2 and not reply["check"]["fallback"]
    assert "Sei in regola" not in reply["text"]


def test_an_invented_quote_is_blocked_then_the_fallback_links_the_id_card_page():
    query = "How much does the ID card cost?"
    client = FakeClient(
        [
            tool("search_official_pages", query=query, service_id=CIE),
            text("«La carta d'identità costa 99 euro per tutti i cittadini» [cie]."),
            text("«La carta costa 99 euro» [cie]."),
        ]
    )
    messages = [{"role": "user", "content": query}]
    reply = agent.run_turn(messages, client=client, lang="en")
    check = reply["check"]
    # the invented quote, its fee no tool returned, and no verbatim quote in an answer
    # from the pages
    assert check["blocked"] == ["invented_quote:1", "ungrounded_fact:number", "unquoted_answer"]
    assert check["blocked_again"] == check["blocked"]
    assert check["fallback"] and not check["ok"] and reply["qa"]
    assert reply["text"] == agent.FALLBACK_QA_TEXT["en"].format(url=CIE_PAGE)
    assert reply["quotes"] == [] and "99 euro" not in str(messages)
    retry = client.calls[2]["messages"][-1]["content"]
    assert "invented_quote" in retry and "« »" in retry


def test_a_quote_cited_from_the_wrong_source_is_regenerated():
    query = "Posso prenotare anche per mia moglie e i miei figli?"
    top = _top(query)
    wrong = "ds549" if top["source_id"] != "ds549" else "cie"
    client = FakeClient(
        [
            tool("search_official_pages", query=query, service_id=CIE),
            tool("find_offices", area="Isola"),
            text(f"«{_sentence(top)}» [{wrong}]"),
            text(f"«{_sentence(top)}» [{top['source_id']}]"),
        ]
    )
    reply = agent.run_turn([{"role": "user", "content": query}], client=client)
    assert reply["check"]["blocked"] == [f"quote_source_mismatch:{wrong}"]
    assert reply["check"]["attempts"] == 2 and not reply["check"]["fallback"]


def test_an_honest_answer_to_an_unanswerable_question_passes():
    query = "Can I travel to London with my Italian CIE?"
    honest = (
        "The saved official pages don't say whether the CIE is accepted in the United Kingdom. "
        f"Please check the official page: {CIE_PAGE} [cie]"
    )
    client = FakeClient([tool("search_official_pages", query=query), text(honest)])
    reply = agent.run_turn(
        [{"role": "user", "content": query}], client=client, service_id=CIE, lang="en"
    )
    assert reply["check"]["ok"], reply["check"]
    assert reply["trace"][0]["output"]["official_page"]["source_id"] == "cie"
    assert evaluate.says_dont_know(reply["text"])


def test_facts_from_passages_need_a_citation_and_a_verbatim_quote():
    query = "Posso prenotare anche per mia moglie e i miei figli?"
    top = _top(query)
    client = FakeClient(
        [
            tool("search_official_pages", query=query, service_id=CIE),
            text("Sì, fino a cinque appuntamenti insieme per la tua famiglia, accedendo con SPID."),
            text(f"Sì: «{_sentence(top)}» [{top['source_id']}]."),
        ]
    )
    reply = agent.run_turn([{"role": "user", "content": query}], client=client)
    assert reply["check"]["blocked"] == ["missing_citation", "unquoted_answer"]
    assert reply["check"]["attempts"] == 2 and not reply["check"]["fallback"]


def test_an_answer_from_the_pages_in_own_words_only_is_regenerated():
    query = "Posso prenotare anche per mia moglie e i miei figli?"
    client = FakeClient(
        [
            tool("search_official_pages", query=query, service_id=CIE),
            text("Sì, fino a cinque appuntamenti insieme per la famiglia [cie]."),
            text("Sì, fino a cinque appuntamenti insieme per la famiglia [cie]."),
        ]
    )
    reply = agent.run_turn([{"role": "user", "content": query}], client=client)
    assert reply["check"]["blocked"] == ["unquoted_answer"] and reply["check"]["fallback"]


def test_search_without_service_uses_the_one_of_earlier_turns():
    first = FakeClient(
        [
            tool("get_checklist", service_id=CIE, answers={"motivo": "pin-puk"}),
            text("Dove puoi venire? [cie]\nOPTIONS: Allo sportello | A domicilio"),
        ]
    )
    messages = [{"role": "user", "content": "Ho perso il PIN"}]
    agent.run_turn(messages, client=first, lang="it")
    second = FakeClient(
        [
            tool("search_official_pages", query="Quanto costa il duplicato del PIN?"),
            text(f"Le pagine ufficiali salvate non lo dicono: {CIE_PAGE} [cie]"),
        ]
    )
    messages.append({"role": "user", "content": "Quanto costa il duplicato del PIN?"})
    reply = agent.run_turn(messages, client=second, lang="it")
    assert reply["trace"][0]["input"] == {"query": "Quanto costa il duplicato del PIN?"}
    assert reply["trace"][0]["output"]["official_page"]["source_id"] == "cie"
    assert reply["check"]["ok"]


def test_quotes_from_an_earlier_turn_still_count():
    query = "Posso prenotare anche per mia moglie e i miei figli?"
    top = _top(query)
    messages = [{"role": "user", "content": query}]
    agent.run_turn(
        messages,
        client=FakeClient(
            [
                tool("search_official_pages", query=query, service_id=CIE),
                text(f"«{_sentence(top)}» [{top['source_id']}]"),
            ]
        ),
    )
    messages.append({"role": "user", "content": "Puoi ripetere?"})
    again = agent.run_turn(
        messages, client=FakeClient([text(f"Certo: «{_sentence(top)}» [{top['source_id']}]")])
    )
    assert again["check"]["ok"] and again["quotes"]


def test_the_system_prompt_states_both_jobs_and_the_official_page():
    assert "search_official_pages" in agent.SYSTEM and "read_source" in agent.SYSTEM
    assert "«" in agent.SYSTEM and CIE_PAGE in agent.SYSTEM
    assert "routes" in agent.SYSTEM and "160 words" in agent.SYSTEM


# ---------------------------------------------------------------- the validator's quote check

TEXTS = [
    (
        "cie",
        "Il rilascio della carta d\u2019identità elettronica avviene **solo su appuntamento** da "
        "prenotare online, selezionando la sede di proprio interesse",
    ),
    (
        "cie-faq-1",
        "- I cittadini stranieri in regola con il permesso di soggiorno possono fare la CIE.",
    ),
]
KNOWN = {"cie", "cie-faq-1", "ds549"}


def _check(reply: str, used_facts: bool = True) -> list[str]:
    return validator.check_reply(
        reply, known_ids=KNOWN, read_ids=KNOWN, used_facts=used_facts, official_texts=TEXTS
    )


@pytest.mark.parametrize(
    "reply",
    [
        "«Il rilascio della carta d'identità elettronica avviene solo su appuntamento» [cie]",
        "«il rilascio della carta d\u2019identità elettronica avviene solo su appuntamento.» [cie]",
        "«Il rilascio della carta […] avviene solo su appuntamento» [cie]",
        "« avviene solo su appuntamento da prenotare online » [cie]",
        "Così dice la pagina: «solo su appuntamento» [cie].",
        "«I cittadini stranieri in regola con il permesso di soggiorno possono fare la CIE» "
        "[cie-faq-1]",
        # a term with no citation right after it: a name, not checked
        "Clicca «Procedi senza registrazione» sulla pagina della prenotazione [cie].",
    ],
)
def test_verbatim_quotes_pass(reply):
    assert _check(reply) == []


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("«La carta costa 10 euro» [cie]", "invented_quote:1"),
        ("«Il rilascio avviene senza appuntamento online» [cie]", "invented_quote:1"),
        ("«solo su appuntamento» [cie] e «si paga con il bancomat» [cie]", "invented_quote:2"),
        ("«avviene solo su appuntamento» [cie-faq-1]", "quote_source_mismatch:cie-faq-1"),
        ("«appuntamento […] Il rilascio della carta» [cie]", "invented_quote:1"),  # out of order
        # a short "term" presented as the page's words (cited) must be on the page
        ("Il Comune scrive «non serve appuntamento» [cie].", "invented_quote:1"),
        ("Clicca «Procedi senza registrazione» [cie].", "invented_quote:1"),
    ],
)
def test_quotes_not_in_the_passages_are_blocked(reply, reason):
    assert reason in _check(reply)


def test_eligibility_words_are_checked_only_outside_verified_quotes():
    inside = (
        "«I cittadini stranieri in regola con il permesso di soggiorno possono fare la CIE» [cie]"
    )
    assert _check(inside.replace("[cie]", "[cie-faq-1]")) == []
    assert _check("Sei in regola. " + inside.replace("[cie]", "[cie-faq-1]")) == [
        "eligibility_claim:in regola"
    ]
    # an invented quote is no shelter for the words inside it
    assert "eligibility_claim:in regola" in _check("«Sei in regola con tutti i documenti» [cie]")
    # without official texts (the replay, older callers) nothing changes: the whole text counts
    assert validator.check_reply(inside, known_ids=KNOWN, read_ids=KNOWN, used_facts=True) == [
        "eligibility_claim:in regola"
    ]


def test_official_texts_are_passages_and_verbatim_quotes_not_paraphrases():
    out = {
        "results": [{"source_id": "a", "passage_id": "a#1", "heading": "H?", "text": "T"}],
        "requirements": [{"source_id": "b", "text_it": "parafrasi", "quote": "Q"}],
        "source_id": "c",
        "passages": [{"passage_id": "c#1", "heading": "", "text": "P"}],
    }
    assert sorted(validator.official_texts(out)) == [
        ("a", "H?"),
        ("a", "T"),
        ("b", "Q"),
        ("c", "P"),
    ]
    trace = [{"tool": "read_source", "input": {}, "output": out}]
    assert validator.used_facts(trace, "Here is what the page says, see the quote below [c].")
    assert (
        validator.describe(["invented_quote:2"], "it") == "citazione che non è nelle pagine lette"
    )


# ---------------------------------------------------------------- evaluation of the question bank


def test_qa_evaluation_refuses_to_run_without_a_key(monkeypatch, capsys, no_network):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-...")
    assert evaluate.main(["--qa", "--only", "cie-booking-04"]) == 2
    assert "--dry-run" in capsys.readouterr().err
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert evaluate.main([]) == 2


def test_qa_dry_run_scores_the_bank_with_a_fake_client(tmp_path, monkeypatch, no_network):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # a dry run needs no key
    real_report = ROOT / "docs" / "eval-results-qa.md"
    before = real_report.stat().st_mtime if real_report.exists() else None
    out = tmp_path / "qa.md"
    ids = ["cie-booking-04", "cie-booking-11", "cie-out-of-scope-01"]
    code = evaluate.main(
        ["--qa", "--dry-run", "--only", *ids, "--out", str(out), "--transcripts", str(tmp_path)]
    )
    md = out.read_text(encoding="utf-8")
    assert code in (0, 1) and "**Dry run**" in md
    assert "| tuning |" in md and "| honesty |" in md and "questions passed" in md
    saved = json.loads((tmp_path / "cie-booking-04.json").read_text(encoding="utf-8"))
    assert saved["tools"][0]["tool"] == "search_official_pages"
    # the fake client's reply went through the real check: a verbatim quote, cited
    assert saved["cited"] and not saved["blocked"]
    assert (real_report.stat().st_mtime if real_report.exists() else None) == before


def test_qa_scoring_rules():
    [booking] = evaluate.qa_questions(only=["cie-booking-04"])
    [unknown] = evaluate.qa_questions(only=["cie-booking-11"])
    evidence = booking["evidence"][0]["quote"]
    quote = {"text": evidence[:60], "source_id": "cie", "url": ""}
    good = {"text": f"«{evidence[:60]}» [cie]", "cited": ["cie"], "quotes": [quote], "check": {}}
    assert evaluate.check_qa(booking, good) == [] and evaluate.evidence_overlap(booking, good)
    # another sentence of the right page counts when it says something (six words or more)
    other = {"text": "Il rilascio della carta avviene solo su appuntamento", "source_id": "cie"}
    assert evaluate.check_qa(booking, {**good, "text": "...", "quotes": [other]}) == []
    title = {"text": "Richiesta", "source_id": "cie"}  # a heading is no evidence
    assert evaluate.check_qa(booking, {**good, "text": "«Richiesta» [cie]", "quotes": [title]}) == [
        "no evidence: no verified quote of an expected source"
    ]
    wrong = {"text": "[ds549]", "cited": ["ds549"], "quotes": [], "check": {}}
    assert len(evaluate.check_qa(booking, wrong)) == 2
    honest = {"text": f"The saved official pages don't say it: {CIE_PAGE} [cie]", "cited": ["cie"]}
    assert evaluate.check_qa(unknown, honest) == []
    made_up = {"text": "You cancel it from the e-mail [cie-faq-03790].", "cited": ["cie-faq-03790"]}
    assert evaluate.check_qa(unknown, made_up) == ["does not say the saved pages don't answer"]
    fallback = {"text": "...", "cited": [], "check": {"fallback": True}}
    assert evaluate.check_qa(unknown, fallback) == []
    assert "safe fallback instead of an answer" in evaluate.check_qa(booking, fallback)
    assert len(evaluate.qa_questions(which="honesty")) == sum(
        not q["answerable"] for q in evaluate.qa_questions()
    )
