"""Adattatore tra il protocollo :class:`ClaudeClient` e l'SDK ``anthropic`` (storia C9).

La chiave non si legge qui: l'applicazione passa un client ``anthropic.Anthropic`` gia' creato.
"""

import anthropic

from onevisit_privacy.errors import ClaudeUnavailableError


class AnthropicFeedbackClient:
    """Implementa ``ClaudeClient.complete`` con l'API Messages."""

    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
        """Invia un solo messaggio utente e restituisce il testo della risposta.

        Gli errori dell'API diventano :class:`ClaudeUnavailableError` (riserva a regole).
        """
        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise ClaudeUnavailableError(type(exc).__name__) from exc
        return "".join(block.text for block in response.content if block.type == "text")
