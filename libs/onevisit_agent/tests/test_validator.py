"""Test del validatore delle risposte (storia C3)."""

import pytest

from onevisit_agent import validate_reply

KNOWN = frozenset({"cie", "ds549"})


def test_reply_with_known_citation_passes() -> None:
    reasons = validate_reply(
        "Serve l'appuntamento [fonte: ds549].", known_source_ids=KNOWN, used_facts=True
    )

    assert reasons == []


def test_validator_blocks_unknown_source_id() -> None:
    reasons = validate_reply(
        "Serve il modulo X [fonte: inventata]", known_source_ids=KNOWN, used_facts=True
    )

    assert reasons == ["unknown_source:inventata"]


@pytest.mark.parametrize(
    "text",
    [
        "Sei idoneo per la carta [fonte: cie]",
        "Ora sei IN REGOLA [fonte: cie]",
        "Il rilascio è garantito [fonte: cie]",
        "You are eligible [fonte: cie]",
        "This is guaranteed [fonte: cie]",
        "Your file is compliant [fonte: cie]",
        "Usted es elegible [fonte: cie]",
        "Está garantizado [fonte: cie]",
        "Usted está en regla [fonte: cie]",
        "Vous êtes éligible [fonte: cie]",
        "C'est garanti [fonte: cie]",
        "Vous êtes en règle [fonte: cie]",
    ],
)
def test_validator_blocks_eligibility_words_in_four_languages(text: str) -> None:
    reasons = validate_reply(text, known_source_ids=KNOWN, used_facts=True)

    assert any(r.startswith("forbidden_phrase:") for r in reasons)


def test_forbidden_words_match_whole_words_only() -> None:
    reasons = validate_reply(
        "Regolamento e garanzia [fonte: cie]", known_source_ids=KNOWN, used_facts=True
    )

    assert reasons == []


def test_validator_blocks_missing_citation_when_facts_used() -> None:
    reasons = validate_reply("Serve l'appuntamento.", known_source_ids=KNOWN, used_facts=True)

    assert reasons == ["missing_citation"]


def test_question_without_facts_needs_no_citation() -> None:
    reasons = validate_reply("È la prima carta?", known_source_ids=KNOWN, used_facts=False)

    assert reasons == []


@pytest.mark.parametrize(
    "text",
    [
        "Você é elegível e o documento está garantido [fonte: cie]",
        "Tudo em ordem, está em regra [fonte: cie]",
        "أنت مؤهل [fonte: cie]",
        "الموعد مضمون [fonte: cie]",
        "Usted es apto para el trámite [fonte: cie]",
        "Good news, you qualify [fonte: cie]",
    ],
)
def test_eligibility_claims_blocked_in_every_supported_language(text: str) -> None:
    reasons = validate_reply(text, known_source_ids=KNOWN, used_facts=True)

    assert any(r.startswith("forbidden_phrase:") for r in reasons)
