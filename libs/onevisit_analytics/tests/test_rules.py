"""Test delle regole deterministiche di classificazione, raggruppamento e bozze (C10)."""

import uuid
from datetime import date

import pytest

from onevisit_analytics import (
    CAUSES,
    Cause,
    GapForDraft,
    NegativeOutcome,
    OpenGap,
    OutcomeInput,
    ProperNameError,
    classify_outcome,
    draft_correction,
    ensure_no_proper_names,
    find_proper_names,
    group_into_gaps,
)


class FakeTextClient:
    """Client Claude finto: restituisce sempre la stessa risposta."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
        self.calls += 1
        return self.reply


def _outcome(**fields: object) -> NegativeOutcome:
    base: dict[str, object] = {
        "case_id": uuid.uuid4(),
        "service_id": "iscrizione-anagrafica-extra-ue",
        "source_id": "residenza-estero",
        "cause": Cause.PROCEDURA_MANCANTE,
        "requirement_id": "documenti-esteri",
        "office_id": "ds549-01",
        "week": date(2026, 9, 7),
    }
    base.update(fields)
    return NegativeOutcome.model_validate(base)


def test_local_cause_enum_matches_the_six_contract_slugs() -> None:
    assert set(CAUSES) == {
        "pagina-incompleta",
        "procedura-non-aggiornata",
        "procedura-mancante",
        "ente-o-ufficio-sbagliato",
        "pagina-chiara-non-seguita",
        "richiesta-non-prevista",
    }


def test_positive_outcome_has_no_cause() -> None:
    assert classify_outcome(OutcomeInput(service_id="carta-identita", outcome="ok")) is None


def test_missing_procedure_is_classified_by_rule() -> None:
    result = classify_outcome(
        OutcomeInput(service_id="x", outcome="missing", missing_procedure=True)
    )

    assert result is not None
    assert result.cause is Cause.PROCEDURA_MANCANTE
    assert result.by == "regola"


def test_invalid_claude_answer_falls_back_to_rule() -> None:
    client = FakeTextClient("non e' JSON")

    result = classify_outcome(
        OutcomeInput(service_id="x", outcome="missing", wrong_office=True), client=client
    )

    assert client.calls == 1
    assert result is not None
    assert result.cause is Cause.ENTE_O_UFFICIO_SBAGLIATO


def test_valid_claude_answer_is_used() -> None:
    client = FakeTextClient(
        '{"cause": "pagina-incompleta", "motivation": "manca il requisito", "confidence": 0.8}'
    )

    result = classify_outcome(OutcomeInput(service_id="x", outcome="missing"), client=client)

    assert result is not None
    assert result.cause is Cause.PAGINA_INCOMPLETA
    assert result.by == "claude"


def test_outcomes_with_same_service_and_page_form_one_new_gap() -> None:
    grouping = group_into_gaps([_outcome(), _outcome(), _outcome()])

    assert len(grouping.gaps) == 1
    assert grouping.gaps[0].is_new
    assert len(grouping.gaps[0].case_ids) == 3
    assert {d.action for d in grouping.decisions} == {"new"}


def test_outcome_joins_existing_open_gap() -> None:
    existing = OpenGap(
        id=uuid.uuid4(),
        service_id="iscrizione-anagrafica-extra-ue",
        source_id="residenza-estero",
        cause=Cause.PROCEDURA_MANCANTE,
        requirement_id="documenti-esteri",
    )

    grouping = group_into_gaps([_outcome()], open_gaps=[existing])

    assert grouping.gaps[0].id == existing.id
    assert grouping.decisions[0].action == "join-existing"


def test_national_source_goes_to_owner_ente() -> None:
    grouping = group_into_gaps(
        [_outcome(source_id="permesso-soggiorno", cause=Cause.ENTE_O_UFFICIO_SBAGLIATO)],
        national_owners={"permesso-soggiorno": "Polizia di Stato"},
    )

    gap = grouping.gaps[0]
    assert gap.recipient == "ente-nazionale"
    assert gap.owner_ente == "Polizia di Stato"
    assert gap.national


def test_clear_page_not_followed_goes_to_assistant() -> None:
    grouping = group_into_gaps([_outcome(cause=Cause.PAGINA_CHIARA_NON_SEGUITA)])

    assert grouping.gaps[0].recipient == "assistente"


def test_gap_fields_never_contain_proper_names() -> None:
    grouping = group_into_gaps([_outcome(), _outcome()])

    gap = grouping.gaps[0]
    assert find_proper_names(gap.title) == []
    assert find_proper_names(gap.summary) == []
    assert all(find_proper_names(e) == [] for e in gap.examples)


def test_proper_name_check_rejects_a_person_name() -> None:
    with pytest.raises(ProperNameError):
        ensure_no_proper_names(["Il caso segnalato da Mario Rossi allo sportello"])


def _gap_for_draft() -> GapForDraft:
    return GapForDraft(
        service_id="iscrizione-anagrafica-extra-ue",
        service_title="Iscrizione anagrafica (extra-UE)",
        source_id="residenza-estero",
        page_title="Residenza dall'estero",
        cause="procedura-mancante",
        requirement_id="documenti-esteri",
        requirement_label="traduzione e legalizzazione dei documenti esteri",
        case_count=6,
    )


def test_rule_draft_has_three_versions_naming_page_and_requirement() -> None:
    draft = draft_correction(_gap_for_draft())

    assert "Residenza dall'estero" in draft.it
    assert "traduzione e legalizzazione" in draft.it
    assert draft.easy_it and draft.en
    assert "Page to change" in draft.en
    assert find_proper_names(draft.it) == []


def test_claude_draft_with_a_name_is_replaced_by_rule_draft() -> None:
    client = FakeTextClient('{"it": "Come dice Giulia Bianchi", "easy_it": "x", "en": "y"}')

    draft = draft_correction(_gap_for_draft(), client=client)

    assert draft.by == "regola"
    assert "Bianchi" not in draft.it
