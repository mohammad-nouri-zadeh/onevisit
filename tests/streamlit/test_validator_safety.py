"""The validator's safety rules on quotes, numbers, links and answers from the pages
(review of the CIE Q&A: short quotes, ellipses, other quotation marks, grounding)."""

from __future__ import annotations

import json

import pytest

from onevisit import kb, tools, validator

KNOWN = set(kb.sources())
PAGES = (
    "cie",
    "cie-ministero-firma-con-cie",
    "cie-faq-03767",
    "cie-faq-00304",
    "cie-faq-00473",
    "cie-faq-00520",
)


def _texts() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for sid in PAGES:
        out += validator.official_texts(
            json.loads(tools.run_tool("read_source", {"source_id": sid}))
        )
    return out


TEXTS = _texts()


def check(reply: str, **extra: object) -> list[str]:
    return validator.check_reply(
        reply, known_ids=KNOWN, read_ids=KNOWN, used_facts=True, official_texts=TEXTS, **extra
    )


# ---------- short quotes are the reply's own words ----------
@pytest.mark.parametrize(
    "reply",
    [
        "Con i tuoi documenti la carta ti è «garantita» [cie].",
        "Sei «idonea» [cie-ministero-firma-con-cie]",
        "La tua carta è «idonea» [cie-ministero-firma-con-cie]",
        "I tuoi documenti sono «validi» [cie].",
        "Your documents are «valid» [cie].",
    ],
)
def test_a_one_word_quote_does_not_shelter_an_eligibility_claim(reply):
    assert any(r.startswith("eligibility_claim:") for r in check(reply)), reply


def test_valid_inside_validita_is_not_a_verbatim_quote():
    found = validator.verify_quotes("«valid» [cie]", TEXTS, KNOWN)
    assert found[0]["status"] == "invented"


def test_a_whole_line_of_the_page_is_a_sentence_and_keeps_its_words():
    # "- idonea a identificare il firmatario;" is a whole list line of the Ministry's page
    quoted = (
        "Il Ministero scrive: «idonea a identificare il firmatario» [cie-ministero-firma-con-cie]"
    )
    assert check(quoted) == []
    q = validator.verify_quotes(quoted, TEXTS, KNOWN)[0]
    assert q["status"] == "verified" and q["exempt"]


# ---------- ellipses ----------
@pytest.mark.parametrize(
    "reply",
    [
        # dropping the page's words around a "non" inverts the rule (Milan opted out of the portal)
        "«tra cui Milano … non … è necessario utilizzare il servizio messo a disposizione sul sito "
        "comune.milano.it» [cie-faq-03767]. Vai direttamente allo sportello.",
        "Sì, ci si può andare: «Con la ricevuta … posso andare all'estero» [cie-faq-00304].",
        "Sì: «No … la ricevuta … è valida per gli spostamenti» [cie-faq-00304].",
        "Sì: «la … carta … è valida» [cie-faq-00473]",
    ],
)
def test_an_ellipsis_cannot_stitch_short_pieces(reply):
    assert "invented_quote:1" in check(reply)


def test_a_question_quoted_without_its_question_mark_is_not_verbatim():
    reply = (
        "Sì, ci si può andare: «Con la ricevuta della CIE posso andare all'estero» [cie-faq-00304]."
    )
    assert "invented_quote:1" in check(reply)


def test_an_ellipsis_quote_is_verified_but_not_exempt_nor_exact():
    reply = (
        "«Il rilascio della carta d'identità elettronica … solo su appuntamento "
        "da prenotare online» [cie]"
    )
    q = validator.verify_quotes(reply, TEXTS, KNOWN)[0]
    assert q["status"] == "verified" and not q["exact"] and not q["exempt"]


def test_more_than_two_ellipses_are_not_verbatim():
    reply = (
        "«Il rilascio della carta d'identità … solo su appuntamento da prenotare … online, "
        "selezionando la sede … di proprio interesse, indicando … nel calendario la data» [cie]"
    )
    assert validator.verify_quotes(reply, TEXTS, KNOWN)[0]["status"] == "invented"


# ---------- terms and quotation marks ----------
def test_a_cited_term_must_be_on_the_page():
    assert "invented_quote:1" in check("Il Comune scrive «non serve appuntamento» [cie].")


@pytest.mark.parametrize(
    "reply",
    [
        "Il tuo passaporto «è valido» [cie].",
        "I tuoi documenti «sono validi».",
        "Hai «tutto il necessario».",
        "You're «all set».",
    ],
)
def test_quotation_marks_never_hide_eligibility_words(reply):
    assert any(r.startswith("eligibility_claim:") for r in check(reply)), reply


@pytest.mark.parametrize(
    "reply",
    [
        "La pagina dice: “La carta è gratuita per tutti i cittadini stranieri” [cie].",
        'The page says: "The card is free for everyone over seventy" [cie].',
        "官方页面说：「70岁以上免费」[cie]。",  # noqa: RUF001 (a Chinese reply's own colon)
        "Die Seite sagt: „Die Karte ist kostenlos für alle“ [cie].",
        "> La carta è gratuita per tutti i cittadini stranieri [cie]",
    ],
)
def test_quotes_in_other_marks_are_checked_too(reply):
    assert "invented_quote:1" in check(reply), reply


def test_a_curly_quote_copied_from_the_page_passes():
    reply = (
        "Il Comune: “selezionando la sede di proprio interesse, indicando nel calendario la data”"
        " [cie]."
    )
    assert check(reply) == []


def test_a_list_copied_onto_one_line_is_still_verbatim():
    reply = (
        "Serve: «muniti della seguente documentazione: - prova della data di partenza; "
        "- copia della "
        "denuncia presentata alle Autorità di Pubblica Sicurezza» [cie-faq-00520]."
    )
    assert check(reply) == []


def test_a_possessive_before_a_quote_that_says_valid_is_caught():
    reply = "La tua carta: «la Carta d'identità è valida» [cie-faq-00473]."
    assert "eligibility_claim:validity" in check(reply)


@pytest.mark.parametrize(
    "claim",
    [
        "La tua carta d'identità è valida [cie].",
        "Il tuo permesso di soggiorno è valido [cie].",
        "Tu tarjeta de identidad es válida [cie].",
    ],
)
def test_validity_claims_with_long_document_names(claim):
    assert "eligibility_claim:validity" in check(claim)


# ---------- grounding: numbers and links come from the tools ----------
def _search(query: str) -> list[dict]:
    out = json.loads(
        tools.run_tool("search_official_pages", {"query": query, "service_id": "carta-identita"})
    )
    return [{"tool": "search_official_pages", "input": {"query": query}, "output": out}]


def _verdict(trace: list[dict], reply: str, user: str, qa: bool = True) -> list[str]:
    return validator.check_reply(
        reply,
        known_ids=KNOWN,
        read_ids=validator.sources_in_trace(trace),
        used_facts=validator.used_facts(trace, reply),
        official_texts=validator.official_texts_in_trace(trace),
        grounding=[*validator.grounding_in_trace(trace), user],
        qa=qa,
    )


def test_a_fact_from_memory_after_a_search_that_found_nothing_is_blocked():
    user = "Posso pagare con Satispay?"
    trace = _search(user)
    reasons = _verdict(
        trace,
        "Sì, allo sportello puoi pagare con Satispay o in bitcoin, costa 22,21 euro [cie].",
        user,
    )
    assert "ungrounded_fact:number" in reasons and "unquoted_answer" in reasons
    honest = (
        "Le pagine salvate non dicono se si può pagare con Satispay: "
        "vedi la pagina ufficiale [cie]."
    )
    assert _verdict(trace, honest, user) == []


def test_numbers_without_any_tool_need_a_source():
    reply = "La CIE costa 22,21 euro, dura 10 anni e non serve appuntamento."
    assert validator.used_facts([], reply)
    reasons = validator.check_reply(
        reply,
        known_ids=KNOWN,
        read_ids=set(),
        used_facts=validator.used_facts([], reply),
        grounding=[],
    )
    assert "missing_citation" in reasons and "ungrounded_fact:number" in reasons


def test_a_short_reply_with_facts_and_a_follow_up_question_needs_a_citation():
    user = "quanto costa la carta d identità?"
    trace = _search(user)
    for reply in (
        "La carta costa 22,21 euro e si paga con il POS. Vuoi sapere altro?",
        "Costa 16,79 euro più diritti, solo in contanti. Ti serve altro?",
        "La CIE costa 99 euro e si ritira dopo 2 giorni: vuoi sapere dove prenotare?",
    ):
        assert "missing_citation" in _verdict(trace, reply, user), reply
    assert _verdict(trace, "Ti serve per un adulto o per un minore?", user) == []


def test_numbers_of_the_person_and_of_the_pages_are_grounded():
    user = "È vero che la carta è gratis per chi ha più di 70 anni?"
    trace = _search(user)
    reply = "Le pagine salvate non dicono nulla di un'esenzione per chi ha più di 70 anni [cie]."
    assert _verdict(trace, reply, user) == []


def test_a_link_no_tool_returned_is_blocked_even_inside_a_verbatim_quote():
    trace = [
        {
            "tool": "read_source",
            "input": {"source_id": "cie-faq-03767"},
            "output": json.loads(tools.run_tool("read_source", {"source_id": "cie-faq-03767"})),
        }
    ]
    page = trace[0]["output"]["passages"][0]["text"]
    assert "comune.milano.it" in page
    altered = (
        "«Per prenotare un [appuntamento](https://pay-cie.example.com) per ottenere» "
        "[cie-faq-03767]"
    )
    assert "ungrounded_url" in _verdict(trace, altered, "come prenoto?")
    assert "ungrounded_url" in _verdict(
        trace, "Paga qui: https://pay-cie.example.com [cie-faq-03767]", "x"
    )


def test_a_link_of_the_page_passes():
    trace = _search("prenotare appuntamento carta identità")
    url = trace[0]["output"]["official_page"]["url"]
    reply = f"Le pagine salvate non dicono altro: vedi {url} [cie]."
    assert "ungrounded_url" not in _verdict(trace, reply, "x")


# ---------- reason codes copy nothing the person wrote ----------
def test_reason_codes_never_copy_the_reply():
    reasons = check("Il tuo passaporto Zorbax è valido [cie].")
    assert "eligibility_claim:validity" in reasons and not any("zorbax" in r for r in reasons)
    long_id = "x" * 45 + "-1"
    reasons = validator.check_reply(
        f"Vedi [{long_id}].", known_ids=KNOWN, read_ids=KNOWN, used_facts=False
    )
    assert reasons == ["unknown_source"]


def test_spanish_reflexive_no_se_is_not_a_dont_know():
    assert not validator.says_dont_know("No se puede pagar con Satispay [cie].")
    assert validator.says_dont_know("No sé si se puede pagar con Satispay.")
    assert validator.says_dont_know("Las páginas guardadas no lo dicen [cie].")
