"""The automatic check on every answer (onevisit/validator.py)."""

from __future__ import annotations

import pytest

from onevisit import validator

KNOWN = {"ds549", "cie", "prenotazione", "residenza-estero"}


def check(text: str, read=("ds549", "cie"), used_facts=True) -> list[str]:
    return validator.check_reply(text, known_ids=KNOWN, read_ids=set(read), used_facts=used_facts)


def test_clean_answer_passes():
    assert (
        check("These are the items the sources list [cie]. The desk officer makes the final check.")
        == []
    )
    assert check("Ecco la checklist [cie] [ds549]: decide l'operatore allo sportello.") == []
    assert check("هذه هي البنود التي تذكرها المصادر [cie]. القرار النهائي لموظف الشباك.") == []


def test_unknown_source_is_blocked():
    assert "unknown_source:ds999" in check("Bring the old card [ds999].")
    assert "unknown_source:comune-cie-2024" in check("Bring the old card [fonte: comune-cie-2024].")


def test_source_not_returned_by_a_tool_is_blocked():
    assert check("Book online [prenotazione].") == ["source_not_read:prenotazione"]


def test_uncited_facts_are_blocked():
    assert check("Bring two passport photos and the police report.") == ["missing_citation"]
    # a short question carries no facts, so it needs no citation
    assert check("Is the card for an adult or a minor?", used_facts=False) == []


@pytest.mark.parametrize(
    "claim",
    [
        "Sei idoneo per la carta [cie].",
        "Con questi documenti sei in regola [cie].",
        "Il rilascio è garantito [cie].",
        "I tuoi documenti sono validi [cie].",
        "You are eligible for the card [cie].",
        "You're all set [cie].",
        "Your documents are valid [cie].",
        "Cumples los requisitos [cie].",
        "Estás en regla [cie].",
        "Vous êtes éligible [cie].",
        "Vos documents sont valides [cie].",
        "أنت مؤهل للحصول على البطاقة [cie].",
        "الموعد مضمون [cie].",
        "你符合条件 [cie]。",
        "保证可以办好 [cie]。",
    ],
)
def test_eligibility_words_are_blocked_in_several_languages(claim):
    reasons = check(claim)
    assert any(r.startswith("eligibility_claim:") for r in reasons), (claim, reasons)


def test_requirement_wording_is_not_a_validity_claim():
    assert check("Bring a valid passport [cie].") == []
    assert check("Porta un documento in corso di validità [cie].") == []


def test_plain_words_and_links_in_brackets_are_not_citations():
    assert (
        validator.cited_source_ids(
            "See [the page](https://www.comune.milano.it) and [note].", KNOWN
        )
        == []
    )
    assert validator.cited_source_ids(
        "Sources [cie, ds549] and [fonte: residenza-estero]", KNOWN
    ) == ["cie", "ds549", "residenza-estero"]


def test_sources_are_collected_from_tool_results():
    trace = [
        {
            "tool": "get_checklist",
            "input": {},
            "output": {
                "requirements": [{"source_id": "cie"}],
                "sources": [{"id": "cie", "url": "u", "publisher": "p"}],
            },
        },
        {"tool": "find_offices", "input": {}, "output": [{"id": "ds549-11", "source_id": "ds549"}]},
        {
            "tool": "get_source",
            "input": {},
            "output": {"id": "prenotazione", "url": "u", "publisher": "p"},
        },
    ]
    assert validator.sources_in_trace(trace) == {"cie", "ds549", "prenotazione"}
    assert validator.used_facts(
        trace, "Here is your checklist with sources, see below for all the items you need."
    )


def test_reasons_never_contain_the_reply_text():
    reasons = check("Mario Rossi, you are eligible [ds999].")
    assert not any("Mario" in r for r in reasons)
    assert "fonte inesistente" in validator.describe(reasons, "it")
