"""Test della pipeline feedback: regex prima, poi il modello finto (storia C9)."""

import json
from typing import Any

from onevisit_privacy import CAUSES, structure_feedback
from onevisit_privacy.testing import FakeClaudeClient

TEXT = (
    "Sono andato allo sportello, la signora Bianchi mi ha detto che mancava la "
    "traduzione del passaporto YA0000000. Scrivetemi a utente@example.org o al 333 000 0000."
)


def test_six_causes() -> None:
    assert len(CAUSES) == 6
    assert "pagina-incompleta" in CAUSES


def test_without_client_only_deterministic_fields() -> None:
    result = structure_feedback("Inutile, ho perso una mattina.", client=None)

    assert result.tone == "frustrato"
    assert result.missing_requirement is None
    assert result.probable_cause is None


def test_model_receives_only_redacted_text() -> None:
    reply = {
        "missing_requirement": "traduzione giurata del passaporto",
        "probable_cause": "pagina-incompleta",
        "tone": "frustrato",
        "suggestion": "Indicare sulla pagina che serve la traduzione del passaporto.",
    }
    client = FakeClaudeClient(responses=[json.dumps(reply)])

    result = structure_feedback(TEXT, client=client, model="claude-haiku-4-5-20251001")

    sent = client.calls[0].prompt
    for value in ("YA0000000", "utente@example.org", "333 000 0000"):
        assert value not in sent
    assert result.probable_cause == "pagina-incompleta"
    assert result.missing_requirement == "traduzione giurata del passaporto"
    assert result.tone == "frustrato"


def test_fields_with_names_or_pii_are_dropped() -> None:
    reply = {
        "missing_requirement": "documento chiesto dalla signora Bianchi",
        "probable_cause": "richiesta-non-prevista",
        "tone": "neutro",
        "suggestion": "Richiamare il cittadino al 333 000 0000",
    }
    client = FakeClaudeClient(responses=[json.dumps(reply)])

    result = structure_feedback(TEXT, client=client)

    assert result.missing_requirement is None
    assert result.suggestion is None
    assert result.probable_cause == "richiesta-non-prevista"


def test_invalid_model_output_falls_back() -> None:
    client = FakeClaudeClient(responses=["non e' JSON", '{"probable_cause": "inventata"}'])

    first = structure_feedback("Grazie, tutto perfetto.", client=client)
    second = structure_feedback("Grazie, tutto perfetto.", client=client)

    assert first.tone == "positivo"
    assert first.probable_cause is None
    assert second.probable_cause is None


def test_api_error_falls_back_to_rules_and_never_raises() -> None:
    import anthropic
    import httpx

    from onevisit_privacy.anthropic_client import AnthropicFeedbackClient

    sdk = anthropic.Anthropic(api_key="sk-ant-fake", max_retries=0)
    request: Any = httpx.Request("POST", "https://api.example.org/v1/messages")

    def boom(**_: object) -> object:
        raise anthropic.APIConnectionError(request=request)

    sdk.messages.create = boom  # type: ignore[method-assign,assignment]

    result = structure_feedback("Mancava la traduzione", client=AnthropicFeedbackClient(sdk))

    assert result.missing_requirement is None and result.probable_cause is None
