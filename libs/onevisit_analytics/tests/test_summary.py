"""Test della sintesi settimanale con regola di riserva (B13)."""

from typing import Any

from onevisit_analytics import CauseCount, Effect, ServiceTrend, WeeklyData, weekly_summary
from onevisit_analytics.summary import SUMMARY_MAX_WORDS


def _data() -> WeeklyData:
    return WeeklyData(
        k_threshold=5,
        trends=[
            ServiceTrend(
                service_id="iscrizione-anagrafica-extra-ue", rate_now=0.93, rate_before=0.7
            ),
            ServiceTrend(service_id="carta-identita", rate_now=0.85, rate_before=0.9),
        ],
        causes=[CauseCount(cause="pagina-incompleta", open_gaps=1, cases=7)],
        effects=[
            Effect(
                service_id="iscrizione-anagrafica-extra-ue",
                requirement_id="documenti-esteri",
                rate_before=0.7,
                rate_after=0.93,
            )
        ],
    )


def test_fallback_summary_mentions_improvement_and_worsening_within_limit() -> None:
    text = weekly_summary(_data())

    assert len(text.split()) <= SUMMARY_MAX_WORDS
    assert "Migliorato: iscrizione-anagrafica-extra-ue da 70% a 93%" in text
    assert "Peggiorato: carta-identita da 90% a 85%" in text
    assert "1)" in text and "3)" in text


def test_claude_summary_is_truncated_to_word_limit() -> None:
    class LongClient:
        def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
            return "parola " * 500

    text = weekly_summary(_data(), client=LongClient())

    assert len(text.split()) == SUMMARY_MAX_WORDS


def test_api_error_falls_back_to_template_summary() -> None:
    import anthropic
    import httpx

    from onevisit_analytics.claude import AnthropicTextClient

    client = AnthropicTextClient("sk-ant-fake", max_retries=0)
    request: Any = httpx.Request("POST", "https://api.example.org/v1/messages")

    def boom(**_: object) -> object:
        raise anthropic.APIConnectionError(request=request)

    client._client.messages.create = boom  # type: ignore[method-assign,assignment]

    text = weekly_summary(_data(), client=client)

    assert "Migliorato: iscrizione-anagrafica-extra-ue da 70% a 93%" in text
