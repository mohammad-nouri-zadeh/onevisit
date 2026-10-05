"""Passage search over the saved official pages (onevisit/search.py). No network, no key.

python -m pytest tests/streamlit/test_search.py -q
"""

from __future__ import annotations

import importlib
import json
import pathlib
import statistics
import sys
import time

import pytest

from onevisit import search

ROOT = pathlib.Path(__file__).resolve().parents[2]
PAGES = ROOT / "data" / "pages"
RETRIEVAL_CASES = ROOT / "data" / "eval" / "qa" / "search-retrieval.json"
SOURCES_HEADER = "id,title,url,publisher,kind,snapshot,retrieved_at,status,notes\n"


def _body(path: pathlib.Path) -> str:
    """The page body after the front matter, read here without the module's parser."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        end = text.index("\n---\n", 3)
        text = text[end + len("\n---\n") :]
    return text.lstrip("\n")


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """An empty data/ folder the module reads instead of the real one; returns write(page)."""
    data = tmp_path / "data"
    (data / "pages").mkdir(parents=True)
    (data / "sources.csv").write_text(SOURCES_HEADER, encoding="utf-8")
    monkeypatch.setattr(search, "DATA", data)
    rows: list[str] = []

    def write(
        source_id: str,
        body: str,
        *,
        kind: str = "page",
        publisher: str = "Comune di Milano",
        services: tuple[str, ...] = ("carta-identita",),
        content_hash: str | None = None,
    ) -> pathlib.Path:
        lines = ["---", f"source_id: {source_id}", f"url: https://example.org/{source_id}"]
        lines += [f"ente: {publisher}", "servizio:" if services else "servizio: []"]
        lines += [f"- {s}" for s in services]
        lines += ["verified_at: '2026-10-04'"]
        if content_hash:
            lines.append(f"content_hash: {content_hash}")
        lines += ["---", "", body]
        path = data / "pages" / f"{source_id}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        rows.append(
            f"{source_id},Title of {source_id},https://example.org/{source_id},{publisher},"
            f"{kind},pages/{source_id}.md,2026-10-04,ok,\n"
        )
        (data / "sources.csv").write_text(SOURCES_HEADER + "".join(rows), encoding="utf-8")
        return path

    return write


# ---------------------------------------------------------------- passages


def test_every_passage_is_a_verbatim_slice_of_its_saved_page():
    pages = sorted(PAGES.glob("*.md"))
    with_passages = 0
    for path in pages:
        body = _body(path)
        passages = search.passages_for(path.stem)
        with_passages += bool(passages)
        for passage in passages:
            assert passage["text"] in body, passage["passage_id"]
            assert passage["text"] == passage["text"].strip()
            assert passage["source_id"] == path.stem
    assert with_passages >= 0.9 * len(pages)


def test_passage_sizes_stay_quotable():
    index = search._index()
    words = [p.words for p in index.passages]
    for passage in index.passages:
        limit = search.FAQ_MAX_WORDS if passage.question else search.HARD_MAX_WORDS
        assert passage.words <= limit, passage.passage_id
        assert passage.words >= 1
    assert search.MIN_WORDS <= statistics.median(words) <= search.MAX_WORDS


def test_menus_breadcrumbs_and_share_buttons_are_left_out():
    for passage in search._index().passages:
        assert "Condividi su Facebook" not in passage.text
        assert "[Home](" not in passage.text
        assert passage.text.strip() != "Estensione - Dimensione"


def test_faq_question_stays_with_its_answer():
    faq_pages = sorted(PAGES.glob("cie-faq-*.md"))
    assert faq_pages
    for path in faq_pages:
        passages = search.passages_for(path.stem)
        assert len(passages) == 1, path.stem
        question = passages[0]["heading"]
        assert question and passages[0]["text"].startswith(question[:20])
        assert passages[0]["text"].endswith(_body(path).rstrip().splitlines()[-1].strip())


def test_faq_question_is_boosted(corpus):
    corpus(
        "faq-zibaldone",
        "## Come si rinnova lo zibaldone?\n\nSi presenta la domanda allo sportello con un "
        "documento valido e la ricevuta del pagamento.\n",
        kind="faq",
    )
    corpus(
        "page-sportello",
        "# Sportello\n\nAllo sportello si presenta la domanda per lo zibaldone con un "
        "documento valido e la ricevuta.\n",
    )
    results = search.search("zibaldone")
    assert [r["source_id"] for r in results] == ["faq-zibaldone", "page-sportello"]
    assert results[0]["heading"] == "Come si rinnova lo zibaldone?"
    assert results[0]["text"].startswith("Come si rinnova lo zibaldone?\n\nSi presenta")


def test_long_section_is_split_at_paragraphs_with_its_heading(corpus):
    paragraphs = [
        f"Paragrafo {n} sulla procedura dello zibaldone: " + " ".join(["parola"] * 60) + "."
        for n in range(6)
    ]
    path = corpus("lunga", "# Titolo\n\n## Procedura\n\n" + "\n\n".join(paragraphs) + "\n")
    passages = search.passages_for("lunga")
    assert len(passages) >= 2
    body = _body(path)
    for passage in passages:
        assert passage["heading"] == "Titolo > Procedura"
        assert passage["text"] in body
        assert passage["text"].startswith("Paragrafo")
        assert len(passage["text"].split()) <= search.HARD_MAX_WORDS


# ---------------------------------------------------------------- ranking


def test_english_spanish_french_arabic_chinese_find_the_italian_passage(corpus):
    corpus(
        "perdita",
        "# Smarrimento\n\nSe hai perso la carta d'identità devi presentare la denuncia "
        "all'autorità di Pubblica Sicurezza e prenotare un nuovo appuntamento.\n",
    )
    corpus(
        "costo",
        "# Costo\n\nIl rilascio della carta d'identità costa 22,20 euro, da pagare allo "
        "sportello in contanti o con bancomat.\n",
    )
    lost = [
        "I lost my ID card",
        "perdí mi documento de identidad",
        "j'ai perdu ma carte d'identité",
        "فقدت بطاقة الهوية",
        "我的身份证丢了",
    ]
    for query in lost:
        assert search.search(query)[0]["source_id"] == "perdita", query
    cost = ["How much does the ID card cost?", "¿Cuánto cuesta el DNI?", "身份证多少钱"]
    for query in cost:
        assert search.search(query)[0]["source_id"] == "costo", query


@pytest.mark.parametrize(
    "query",
    [
        "How much does the ID card cost?",
        "¿Cuánto cuesta el DNI?",
        "Combien coûte la carte d'identité ?",
        "كم تكلفة بطاقة الهوية",
        "身份证多少钱",
    ],
)
def test_real_pages_answer_the_cost_in_any_language(query):
    results = search.search(query, service_id="carta-identita", k=3)
    assert any("22,20" in r["text"] and r["lang"] == "it" for r in results), results


def test_real_pages_answer_a_lost_card_not_a_lost_pin():
    results = search.search("I lost my ID card", service_id="carta-identita", k=3)
    top = results[0]
    assert top["lang"] == "it"
    assert "PIN" not in top["heading"]
    assert any(w in top["text"].lower() for w in ("smarri", "perso", "denuncia"))


def test_query_terms_map_words_to_shared_concepts():
    assert {"§lost", "§idcard"} <= set(search.query_terms("I lost my ID card"))
    assert {"§lost", "§idcard"} <= set(search.query_terms("我的身份证丢了"))
    assert {"§stolen", "§idcard"} <= set(search.query_terms("بطاقة الهوية مسروقة"))
    assert "§elderly" in search.query_terms("I'm 72, is my card valid forever?")
    terms = search.query_terms("ho perso la carta d'identità")
    assert terms["§lost"] == 1.0
    assert terms["pers"] == search.COVERED_WEIGHT


def test_retrieval_cases_find_an_expected_page():
    report = search.evaluate(RETRIEVAL_CASES)
    assert report["cases"] >= 40
    assert report["hit_at_5"] >= 0.9, report["misses"]
    assert report["hit_at_1"] >= 0.75


# ---------------------------------------------------------------- filters, freshness, edges


def test_service_filter_keeps_the_service_pages():
    index = search._index()
    cie = search._service_pages(index, "carta-identita")
    residence = search._service_pages(index, "cambio-residenza")
    assert cie and residence and "cie" in cie and "cie" not in residence
    for result in search.search("costo documenti", service_id="cambio-residenza", k=10):
        assert result["source_id"] in residence
    for result in search.search("documenti permesso di soggiorno", "carta-identita", k=10):
        assert result["source_id"] in cie
    assert search.search("costo", service_id="no-such-service") == []


def test_service_filter_reads_the_page_front_matter(corpus):
    corpus("uno", "# Uno\n\nLo zibaldone si rinnova allo sportello.\n", services=("servizio-a",))
    corpus("due", "# Due\n\nLo zibaldone si rinnova online.\n", services=("servizio-b",))
    assert [r["source_id"] for r in search.search("zibaldone", "servizio-a")] == ["uno"]
    assert [r["source_id"] for r in search.search("zibaldone", "servizio-b")] == ["due"]
    assert len(search.search("zibaldone")) == 2


def test_new_page_is_found_without_restart(corpus):
    corpus("vecchia", "# Vecchia\n\nUna pagina sulla carta d'identità allo sportello.\n")
    assert search.search("zibaldone") == []
    pages_before = search.index_stats()["pages"]
    corpus("nuova", "# Nuova\n\nLo zibaldone si ritira allo sportello di via Larga.\n")
    results = search.search("zibaldone")
    assert [r["source_id"] for r in results] == ["nuova"]
    assert search.index_stats()["pages"] == pages_before + 1


@pytest.mark.parametrize(
    "query", ["", "   ", "?!?", "il la di per", "xqzv blorpt", "the of and", "§lost"]
)
def test_empty_or_meaningless_query_returns_nothing(query, corpus):
    corpus("pagina", "# Pagina\n\nSe hai perso la carta d'identità serve la denuncia.\n")
    expected = [] if query != "§lost" else ["pagina"]  # '§' is not a word: it reads "lost"
    assert [r["source_id"] for r in search.search(query)] == expected


def test_k_zero_and_wrong_type_return_nothing():
    assert search.search("carta d'identità", k=0) == []
    assert search.search(None) == []  # type: ignore[arg-type]  # a tool may pass null


def test_same_query_same_results_in_a_stable_order():
    query = "Can my child travel abroad with the ID card?"
    first = search.search(query, service_id="carta-identita", k=8)
    second = search.search(query, service_id="carta-identita", k=8)
    assert first == second
    assert len(first) == 8
    scores = [r["score"] for r in first]
    assert scores == sorted(scores, reverse=True)
    per_page: dict[str, int] = {}
    for r in first:
        per_page[r["source_id"]] = per_page.get(r["source_id"], 0) + 1
    assert max(per_page.values()) <= search.PER_SOURCE


def test_ties_are_ordered_by_source_id(corpus):
    text = "# Pagina\n\nLo zibaldone si rinnova allo sportello.\n"
    corpus("b-pagina", text)
    corpus("a-pagina", text)
    results = search.search("zibaldone")
    assert [r["source_id"] for r in results] == ["a-pagina", "b-pagina"]
    assert results[0]["score"] == results[1]["score"]


def test_lang_boosts_the_reader_language_without_filtering(corpus):
    corpus("italiano", "# Costo\n\nLa carta d'identità costa 22,20 euro allo sportello.\n")
    corpus("inglese", "# Cost\n\nThe identity card costs 22.20 euro at the desk, paid by card.\n")
    plain = {r["source_id"]: r["score"] for r in search.search("costo carta")}
    english = {r["source_id"]: r["score"] for r in search.search("costo carta", lang="en")}
    assert set(english) == set(plain) == {"italiano", "inglese"}
    # Scores are rounded to 3 decimals: compare within that rounding.
    assert english["inglese"] == pytest.approx(plain["inglese"] * search.LANG_BOOST, abs=2e-3)
    assert english["italiano"] == pytest.approx(plain["italiano"], abs=1e-3)


def test_result_carries_what_a_citation_needs(corpus):
    corpus("pagina", "# Pagina\n\nLo zibaldone si rinnova allo sportello.\n", kind="page")
    result = search.search("zibaldone")[0]
    assert set(result) >= {
        "source_id",
        "title",
        "publisher",
        "url",
        "saved_at",
        "heading",
        "text",
        "score",
    }
    assert result["title"] == "Title of pagina"
    assert result["publisher"] == "Comune di Milano"
    assert result["url"] == "https://example.org/pagina"
    assert result["saved_at"] == "2026-10-04"
    assert result["heading"] == "Pagina"


def test_hand_edited_page_is_reported(corpus):
    corpus("integra", "# Integra\n\nTesto salvato.\n")
    corpus("ritoccata", "# Ritoccata\n\nTesto cambiato.\n", content_hash="sha256:" + "0" * 64)
    assert search.index_stats()["hash_mismatches"] == ["ritoccata"]


# ---------------------------------------------------------------- tool and speed


def test_tool_result_is_json_with_sources_or_a_note():
    args = {"query": "quanto costa la carta d'identità", "service_id": "carta-identita"}
    payload = json.loads(search.run_tool(args))
    assert payload["results"]
    for result in payload["results"]:
        assert result["source_id"] and result["url"].startswith("https://")
        assert result["text"] and result["saved_at"]
    empty = json.loads(search.run_tool({"query": "xqzv blorpt"}))
    assert empty["results"] == [] and "official page" in empty["note"]
    assert search.TOOL["input_schema"]["required"] == ["query"]


def test_index_builds_in_under_a_second_and_queries_are_fast():
    search._build.cache_clear()
    started = time.perf_counter()
    stats = search.index_stats()
    build_s = time.perf_counter() - started
    assert stats["pages"] >= 100 and stats["passages"] >= stats["pages"]
    assert build_s < 2.0  # about 0.4 s on a laptop; the margin is for busy test machines
    queries = ["I lost my ID card", "¿Cuánto cuesta el DNI?", "身份证多少钱", "foto requisiti"]
    started = time.perf_counter()
    for _ in range(10):
        for query in queries:
            search.search(query, service_id="carta-identita")
    average_ms = (time.perf_counter() - started) * 1000 / (10 * len(queries))
    assert average_ms < 50


# ---------------------------------------------------------------- the ID card question bank


@pytest.fixture(scope="module")
def bank_report():
    """run_retrieval.measure() on the tuning questions of data/eval/qa (never the holdout)."""
    qa = str(ROOT / "data" / "eval" / "qa")
    if qa not in sys.path:
        sys.path.insert(0, qa)
    check_bank = importlib.import_module("check_bank")
    run_retrieval = importlib.import_module("run_retrieval")
    tuning = [q for q in check_bank.load_bank()["questions"] if not q["holdout"]]
    return run_retrieval.measure(tuning)


def test_bank_italian_and_english_questions_find_the_answer(bank_report):
    main = bank_report["groups"]["tuning/it-en"]
    assert main["n"] >= 130
    failures = [r["id"] for r in bank_report["rows"] if r["answerable"] and r["lang"] in "it en"]
    assert main["hit@3"] >= 0.85, failures
    assert main["hit@5"] >= 0.90
    assert main["page@5"] >= 0.93
    assert main["hit@1"] >= 0.65


def test_bank_other_languages_find_the_answer(bank_report):
    other = bank_report["groups"]["tuning/other"]
    assert other["n"] >= 25
    assert other["hit@3"] >= 0.80
    for lang in ("es", "fr", "ar", "zh", "uk", "bn"):
        assert bank_report["groups"][f"tuning/lang:{lang}"]["hit@5"] > 0, lang


def test_bank_answerable_questions_are_mostly_confident(bank_report):
    assert bank_report["groups"]["tuning/all"]["confident"] >= 0.93


def test_bank_out_of_scope_questions_are_never_confident(bank_report):
    out_of_scope = [r for r in bank_report["rows"] if r["facet"] == "out_of_scope"]
    assert len(out_of_scope) >= 5
    assert all(r["confident"] is False for r in out_of_scope), out_of_scope


# ---------------------------------------------------------------- query reading


def test_a_typo_is_read_as_the_known_word_one_edit_away():
    index = search._index()
    assert search._correct(index, "expierd") == "expired"
    assert search._correct(index, "documneti") == "documenti"
    assert search._correct(index, "booth") == "booth"  # a concept word: never "both"
    assert search._correct(index, "carta") == "carta"
    assert search._correct(index, "zxqwv") == "zxqwv"
    assert "§expiry" in search.query_terms("my id card expierd last month")


def test_chat_shorthand_is_read_as_the_word():
    assert "§missed_delivery" in search.query_terms("il postino nn mi ha trovato a casa")


def test_bengali_and_ukrainian_words_are_not_split():
    assert search._WORD.findall(search._fold("আইডি কার্ড")) == ["আইডি", "কার্ড"]
    assert {"§idcard", "§cost"} <= set(search.query_terms("আইডি কার্ড করতে কত খরচ হয়?"))
    assert {"§idcard", "§minor", "§travel"} <= set(
        search.query_terms("Чи може моя дитина виїхати за кордон з ID-карткою?")
    )


def test_how_long_it_lasts_is_not_when_it_expired():
    assert "§duration" in search.query_terms("Quanto dura la carta d'identità?")
    assert "§duration" in search.query_terms("How many years is the ID card valid?")
    assert "§expiry" not in search.query_terms("Quanto dura la carta d'identità?")
    assert "§expiry" in search.query_terms("La mia carta è scaduta")


def test_question_words_weigh_less_and_are_not_a_topic(corpus):
    corpus("foto", "## Quante foto servono?\n\nServono due fotografie recenti a colori.\n")
    corpus("sedi", "## Sedi anagrafiche\n\nLe sedi anagrafiche sono in via Larga e nei municipi.\n")
    results = search.search("Quante sono le sedi anagrafiche?")
    assert results[0]["source_id"] == "sedi"
    assert search.query_terms("quante sedi")["§how_many"] < 1.0


def test_a_heading_naming_a_related_concept_is_not_another_topic(corpus):
    text = "Se hai perso la carta d'identità presenta la denuncia ai Carabinieri.\n"
    corpus("furto-smarrimento", "## Furto e smarrimento\n\n" + text)
    corpus("smarrimento-urgenza", "## Smarrimento e urgenza\n\n" + text)
    results = search.search("Ho perso la carta d'identità")
    assert [r["source_id"] for r in results] == ["furto-smarrimento", "smarrimento-urgenza"]


def test_a_page_that_repeats_a_section_gives_it_once(corpus):
    section = "#### Come si blocca la carta?\n\nChiama il numero verde e blocca la carta.\n\n"
    corpus("faq-ministero", "## In evidenza\n\n" + section + "## Sicurezza\n\n" + section)
    results = search.search("come si blocca la carta", per_source=5)
    assert len(results) == 1


# ---------------------------------------------------------------- confidence


def test_best_answer_says_why_it_is_not_confident():
    service = "carta-identita"
    assert search.best_answer("xqzv blorpt", service)["reason"] == "no_match"
    licence = search.best_answer("Come rinnovo la patente di guida?", service)
    assert licence["reason"] == "other_document" and not licence["confident"]
    assert licence["passages"]  # the passages are still given, for Claude to read
    for off_topic in ("Where can I buy a SIM card?", "Dove posso parcheggiare vicino al Duomo?"):
        weak = search.best_answer(off_topic, service)
        assert not weak["confident"], off_topic
        assert weak["reason"] in {"weak_match", "unknown_words"}, off_topic
    cost = search.best_answer("Quanto costa la carta d'identità?", service)
    assert cost["confident"] and cost["reason"] == "ok"
    assert any("22,20" in p["text"] for p in cost["passages"])


def test_every_result_carries_its_confidence():
    results = search.search("I lost my ID card", service_id="carta-identita", k=5)
    assert results[0]["confident"] is True
    for result in results:
        assert 0.0 <= result["confidence"] <= 1.0
        if result["confident"]:
            assert result["score"] >= search.RELATIVE_TO_TOP * results[0]["score"] - 1e-3


def test_tool_result_tells_claude_when_the_match_is_weak():
    args = {"query": "How do I get SPID?", "service_id": "carta-identita"}
    payload = json.loads(search.run_tool(args))
    assert payload["confident"] is False and payload["reason"] == "other_document"
    assert payload["results"] and "say you don't know" in payload["note"]
    good = json.loads(
        search.run_tool({"query": "I lost my ID card", "service_id": "carta-identita"})
    )
    assert good["confident"] is True and "note" not in good


# ---------------------------------------------------------------- review fixes (2026-10-05)


def _cie_passage(fragment: str) -> dict:
    """The passage of the City's CIE page that holds `fragment` (skips if the page changed)."""
    found = [p for p in search.passages_for("cie") if fragment in p["text"].replace("\xa0", " ")]
    if not found:
        pytest.skip(f"data/pages/cie.md no longer holds {fragment!r}")
    return found[0]


def test_a_tab_label_stays_inside_its_section_on_the_city_page():
    provisional = _cie_passage("euro 5,42")  # the provisional card's own list
    assert "provvisoria" in provisional["heading"]
    assert provisional["heading"].endswith("Documenti da presentare")
    cost = _cie_passage("22,20")
    assert "domicilio" not in cost["heading"]
    assert cost["heading"].endswith("Costo e durata")
    documents = _cie_passage("Tessera sanitaria (Carta Nazionale dei Servizi) o codice fiscale")
    assert documents["heading"] == "Carta d'identità > Documenti da presentare"


def test_heading_levels_read_labels_but_keep_ordinary_sections(corpus):
    labels = (
        "# Servizio\n\n## Documenti da presentare\n\nLista dei documenti A.\n\n"
        "### Sezione uno\n\nTesto.\n\n### Sezione due\n\nTesto.\n\n"
        "## Documenti da presentare\n\nLista dei documenti B.\n\n"
        "### Altra documentazione\n\n## Casi specifici\n\nLista dei documenti C.\n\n"
        "## A domicilio\n\nLista dei documenti D.\n\n"
        "### Costo\n\nTesto sul costo della carta.\n"
    )
    assert search._heading_levels(labels) == [1, 7, 3, 3, 7, 3, 7, 7, 3]
    corpus("servizio", labels)
    headings = {p["text"]: p["heading"] for p in search.passages_for("servizio")}
    assert headings["Lista dei documenti B."] == "Servizio > Sezione due > Documenti da presentare"
    assert headings["Lista dei documenti D."] == "Servizio > Altra documentazione > A domicilio"
    assert headings["Testo sul costo della carta."] == "Servizio > Costo"
    ordinary = "# T\n\n## A\n\nTesto.\n\n### A.1\n\nTesto.\n\n## B\n\nTesto.\n\n### B.1\n\nTesto.\n"
    assert search._heading_levels(ordinary) == [1, 2, 3, 2, 3]


def test_the_provisional_documents_list_is_not_the_cie_answer():
    for query in (
        "quante foto devo portare per la carta d'identità?",
        "Qual è il prezzo della CIE e quali documenti devo presentare?",
    ):
        results = search.search(query, service_id="carta-identita", k=3)
        assert not any("provvisori" in r["heading"].lower() for r in results), query
        assert not any("5,42" in r["text"] for r in results), query
    both = search.search(
        "Qual è il prezzo della CIE e quali documenti devo presentare?", "carta-identita", k=3
    )
    assert any("22,20" in r["text"] for r in both)
    assert {r["part"] for r in both} == {
        "Qual è il prezzo della CIE",
        "quali documenti devo presentare",
    }


@pytest.mark.parametrize(
    ("query", "wrong"),
    [
        ("how much time does it take to get the card after the appointment", "§cost"),
        ("è cara la carta d'identità?", "§face"),
        ("I'm a European citizen living in Milan, can I get the CIE?", "§travel"),
        ("What if the father is absent and can't sign the consent?", "§missed_delivery"),
        ("Can I get a CIE with refugee status?", "§tracking"),
        ("I found out my card expires next week", "§found"),
        ("I just arrived in Milan, can I get an ID card?", "§delivery"),
        ("¿Abren por la mañana las oficinas?", "§urgent"),
        ("ho subito un furto della carta", "§urgent"),
        ("Come si usa la CIE per entrare nell'app IO?", "§travel"),
        ("ne servono due?", "§birth"),
        ("Cosa dice la legge sulle carte cartacee?", "§read_card"),
        ("serve il certificato di residenza?", "§medical_certificate"),
        ("il CAP dell'indirizzo di spedizione", "§head_covering"),
        ("does the card come with a PIN?", "§accompanied"),
        ("the official website to book", "§staff"),
        ("I'm missing a document for the appointment", "§lost"),
        ("i codici arrivano in busta separata?", "§civil_status"),
    ],
)
def test_common_words_do_not_bring_another_topic(query, wrong):
    assert wrong not in search.query_terms(query)


def test_the_right_concepts_for_those_phrases():
    assert "§timing" in search.query_terms("how much time does it take")
    assert "§foreigner" in search.query_terms("I'm a European citizen")
    assert "§hours" in search.query_terms("¿Abren por la mañana?")
    assert "§stolen" in search.query_terms("ho subito un furto della carta")
    assert "§urgent" in search.query_terms("mi serve subito la carta")
    assert "§delivery" in search.query_terms("quando arriva la carta?")
    assert "§no_document" in search.query_terms("I'm missing a document")
    assert "§cost" in search.query_terms("quanto si spende per la cie?")


@pytest.mark.parametrize(
    ("query", "concept", "expected"),
    [
        ("vale 10 anni?", "§minor", False),
        ("dura 10 anni la carta?", "§minor", False),
        ("posso rinnovarla se mancano meno di 6 mesi?", "§minor", False),
        ("is it ready in under 5 minutes?", "§minor", False),
        ("una validità di 10 anni", "§minor", False),
        ("mio figlio ha 10 anni", "§minor", True),
        ("un bambino di 12 anni", "§minor", True),
        ("my son is 10, can he travel?", "§minor", True),
        ("she's 9 years old", "§minor", True),
        ("mi hijo tiene 8 años", "§minor", True),
        ("under 18", "§minor", True),
        ("entro il termine di 90 giorni", "§elderly", False),
        ("costa più di 70 euro?", "§elderly", False),
        ("My dad is 81, will his new CIE expire?", "§elderly", True),
        ("ho 72 anni", "§elderly", True),
        ("I'm 72, is my card valid forever?", "§elderly", True),
        ("Ma mère a 78 ans", "§elderly", True),
    ],
)
def test_ages_are_read_only_as_ages(query, concept, expected):
    assert (concept in search.query_terms(query)) is expected


def test_domiciled_is_one_concept_whatever_the_gender():
    for word in ("domiciliato", "domiciliata", "domiciliati", "domiciliate"):
        terms = search.query_terms(f"Sono residente a Torino ma {word} a Milano")
        assert "§other_comune" in terms and "§residence" in terms, word


@pytest.mark.parametrize(
    ("query", "wrong"),
    [
        ("أين يجب أن أتوجه لتجديد بطاقة الهوية؟", "§face"),  # وجه inside أتوجه
        ("ما هي عملية الحصول على بطاقة الهوية؟", "§workplace"),  # عملي inside عملية
        ("الحماية الدولية", "§guardian"),  # ولي inside الدولية
        ("ما هو الأمر؟", "§parent"),  # الأم inside الأمر
        ("الخلفية باللون الأبيض", "§parent"),  # الأب inside الأبيض
        ("كيف يحصلون عليها", "§colour"),  # لون inside يحصلون
        ("أنواع مختلفة", "§damaged"),  # تلف inside مختلفة
        ("Яка інформація потрібна для оформлення?", "§form"),  # форм inside інформація
        ("серед документів", "§weekday"),  # серед: among, not Wednesday
        ("це дійсно так?", "§validity"),  # дійсно: really
        ("আমার সঙ্গে কী নিয়ে যেতে হবে?", "§accompanied"),  # সঙ্গে: with me
    ],
)
def test_script_words_are_not_found_inside_other_words(query, wrong):
    assert wrong not in search.query_terms(query)


def test_script_words_still_find_their_own_forms():
    assert "§foreigner" in search.query_terms("بطاقة الهوية للأجانب")  # ل + ل + أجانب
    assert "§face" in search.query_terms("وجهي في الصورة")  # my face
    assert "§background" in search.query_terms("لون الخلفية")
    assert "§colour" in search.query_terms("لون الخلفية")
    assert "§documents" in search.query_terms("Яка інформація потрібна для ID-картки?")
    assert "§asylum" in search.query_terms("هل الحماية الدولية تكفي؟")


def test_a_real_word_is_not_corrected_into_another():
    index = search._index()
    for word in ("votare", "avuto", "treno", "multa", "tarda", "lending", "defunto"):
        assert search._correct(index, word) == word, word
    assert search._correct(index, "smarita") == "smarrita"  # a letter dropped
    assert search._correct(index, "oficinas") == "oficina"
    terms = search.query_terms("Mi serve la carta d'identità per votare?")
    assert "§travel" not in terms


def test_bringing_another_document_is_a_question_about_this_service():
    for query in (
        "Devo portare il permesso di soggiorno all'appuntamento?",
        "Serve la tessera sanitaria?",
        "Should I bring my passport to the appointment?",
    ):
        answer = search.best_answer(query, "carta-identita")
        assert answer["reason"] != "other_document", query
    permit = search.search(
        "Devo portare il permesso di soggiorno all'appuntamento?", "carta-identita", k=3
    )
    assert any("permesso di soggiorno" in r["text"] for r in permit)
    for query in (
        "Come rinnovo la patente di guida?",
        "How do I book an appointment for an Italian passport?",
    ):
        assert search.best_answer(query, "carta-identita")["reason"] == "other_document", query


def test_a_question_about_nothing_but_the_card_is_never_confident():
    answer = search.best_answer("x x x x x carta", "carta-identita")
    assert not answer["confident"] and answer["reason"] == "weak_match"
    assert answer["confidence"] < 1.0
    assert search.best_answer("What exactly is the CIE?", "carta-identita")["confident"]


def test_a_low_score_is_never_confident(corpus):
    corpus("pagina", "# Pagina\n\nLo zibaldone si rinnova allo sportello con la ricevuta.\n")
    corpus("altra", "# Altra\n\nIl modulo si consegna in via Larga.\n")
    for result in search.search("zibaldone"):
        assert result["score"] >= search.MIN_SCORE or not result["confident"]


def test_unread_words_of_another_script_lower_the_confidence():
    concepts = search._concepts(search._stat(search.SYNONYMS_FILE))
    assert search._script_gaps(concepts, "بطاقة الهوية") == 0
    assert search._script_gaps(concepts, "هل يوجد مترجم يتكلم العربية") >= 3
    assert search._script_gaps(concepts, "我在米兰") == 0  # function words and Milan
    read = search.best_answer("بطاقة الهوية مفقودة", "carta-identita")
    unread = search.best_answer("بطاقة الهوية مفقودة مترجم يتكلم العربية الحماية", "carta-identita")
    assert unread["confidence"] < read["confidence"]


def test_results_carry_their_own_date_and_kind():
    index = search._index()
    for result in search.search("Ho perso la carta d'identità", "carta-identita", k=5):
        assert {"updated_at", "kind", "saved_at"} <= set(result)
    circulars = [p for sid, p in index.pages.items() if sid.startswith("circ-")]
    assert circulars and all(p.kind == "circular" for p in circulars)
    assert all(p.updated_at for p in circulars)
    faq = index.pages.get("cie-faq-00305")
    if faq is not None:
        assert faq.updated_at == "2025-10-23"


def test_page_dates_are_read_from_the_page():
    assert search._page_date("Testo.\n\nUltimo aggiornamento: 02/10/2026\n") == "2026-10-02"
    assert search._page_date("# Notizia\n\nData:\n19 gennaio 2026\n\nTesto.") == "2026-01-19"
    assert search._page_date("29/12/2015\n (modificato il 18/02/2026)") == "2026-02-18"
    assert search._page_date("x", "https://x.it/circ-004-servdemo-03-04-2017.pdf") == "2017-04-03"
    assert search._page_date("Roma\n\n02/02/2026\n\nOGGETTO: ...") == "2026-02-02"
    assert search._page_date("Nessuna data qui.") == ""


def test_old_news_and_circulars_rank_lower(corpus):
    text = "Lo zibaldone si prenota online e si ritira allo sportello di via Larga."
    corpus("pagina", f"# Zibaldone\n\n{text}\n\nUltimo aggiornamento: 01/10/2026\n")
    corpus("notizia-nuova", f"# Zibaldone\n\nData:\n01 settembre 2026\n\n{text}\n", kind="news")
    corpus("notizia-vecchia", f"# Zibaldone\n\nData:\n02 gennaio 2022\n\n{text}\n", kind="news")
    corpus("circ-x-2015", f"# Zibaldone\n\n01/02/2015\n\n{text}\n", kind="pdf")
    scores = {r["source_id"]: r["score"] for r in search.search("zibaldone", k=10)}
    assert scores["pagina"] > scores["notizia-nuova"] > scores["notizia-vecchia"]
    assert scores["notizia-vecchia"] > scores["circ-x-2015"]
    kinds = {r["source_id"]: r["kind"] for r in search.search("zibaldone", k=10)}
    assert kinds["circ-x-2015"] == "circular" and kinds["notizia-vecchia"] == "news"


def test_numbers_of_identifiers_are_not_read():
    assert "81" not in search.query_terms("Circolare n.81/2023")
    assert "0017063" not in search.query_terms("prot. N.0017063")
    terms = search.query_terms("My dad is 81")
    assert terms["81"] < 1.0 and "§elderly" in terms


def test_a_message_with_two_questions_is_searched_one_at_a_time():
    assert search._parts("Qual è il prezzo della CIE e quali documenti devo presentare?") == [
        "Qual è il prezzo della CIE",
        "quali documenti devo presentare",
    ]
    assert search._parts("Quanto costa la carta d'identità?") == [
        "Quanto costa la carta d'identità?"
    ]
    # a part with nothing of its own stays with the question before it
    assert len(search._parts("Quanto costa il passaporto? e la carta d'identità?")) == 1
    assert "one search per question" in search.TOOL["description"]


def test_for_what_the_city_sets_its_own_page_comes_first():
    results = search.search("Quanto costa la carta d'identità?", "carta-identita", k=3)
    assert results[0]["publisher"] == "Comune di Milano"
    assert "22,20" in results[0]["text"]


def test_a_page_in_review_is_not_searchable(corpus):
    corpus("letta", "# Letta\n\nLo zibaldone si rinnova allo sportello di via Larga.\n")
    corpus("in-revisione", "# Nuova\n\nLo zibaldone si rinnova online con lo SPID.\n")
    sources = search.DATA / "sources.csv"
    text = sources.read_text(encoding="utf-8")
    sources.write_text(
        text.replace("in-revisione.md,2026-10-04,ok,", "in-revisione.md,2026-10-04,review,")
    )
    assert [r["source_id"] for r in search.search("zibaldone")] == ["letta"]
