"""Client Claude minimo usato dall'analisi (storie C10, B13).

La libreria non legge l'ambiente: l'applicazione crea il client con la chiave e lo passa.
Senza client, ogni funzione usa la regola deterministica di riserva.
"""

from typing import Protocol

import anthropic

from onevisit_analytics.errors import ClaudeOutputError

# Modello di default per classificazione, bozze e sintesi (docs/contracts.md).
DEFAULT_MODEL = "claude-sonnet-5-5"


class TextClient(Protocol):
    """Dipendenza verso Claude: un prompt in ingresso, il testo della risposta in uscita."""

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
        """Restituisce il testo della risposta."""
        ...


class AnthropicTextClient:
    """Adattatore sull'SDK ``anthropic`` che implementa :class:`TextClient`."""

    def __init__(self, api_key: str, *, timeout_s: float = 30.0, max_retries: int = 2) -> None:
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout_s, max_retries=max_retries
        )

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> str:
        """Chiama l'API Messages e concatena i blocchi di testo.

        Errori dell'API (chiave non valida, 429, 5xx, timeout) diventano
        :class:`ClaudeOutputError`, che le funzioni dell'analisi gestiscono con la riserva.
        """
        try:
            message = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise ClaudeOutputError(f"API Claude non disponibile ({type(exc).__name__})") from exc
        return "".join(block.text for block in message.content if block.type == "text")
