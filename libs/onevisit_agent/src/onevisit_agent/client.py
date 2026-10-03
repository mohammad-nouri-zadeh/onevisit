"""Client verso Claude (storia C3).

``ClaudeClient`` è il protocollo minimo che l'agente usa: un sottoinsieme di
``messages.create``. ``AnthropicClaudeClient`` lo implementa con l'SDK ufficiale, con timeout
e nuovi tentativi con attesa crescente (gestiti dall'SDK). Le risposte sono normalizzate in
``ClaudeResponse``, così l'agente e il client finto non dipendono dai tipi dell'SDK.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from onevisit_agent.errors import ClaudeClientError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContentBlock:
    """Blocco di contenuto normalizzato: ``text`` oppure ``tool_use``."""

    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClaudeResponse:
    """Risposta normalizzata. ``raw_content`` è il contenuto da rimandare tale e quale."""

    content: list[ContentBlock]
    stop_reason: str | None
    raw_content: list[dict[str, Any]]


class ClaudeClient(Protocol):
    """Sottoinsieme di ``messages.create`` usato dall'agente."""

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ClaudeResponse: ...


def _block_to_raw(block: Any) -> dict[str, Any]:
    """Converte un blocco dell'SDK nel dizionario da rimandare all'API."""
    raw: dict[str, Any] = block.to_dict()
    return raw


class AnthropicClaudeClient:
    """Implementazione di ``ClaudeClient`` con l'SDK ``anthropic``."""

    def __init__(self, api_key: str, *, timeout_s: float = 30, max_retries: int = 2) -> None:
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout_s, max_retries=max_retries
        )

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ClaudeResponse:
        """Chiama ``messages.create``; ogni errore dell'API diventa ``ClaudeClientError``."""
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        kwargs.update(_model_options(model))
        try:
            message = self._client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            # Solo il tipo dell'errore: il messaggio potrebbe riportare parti della richiesta.
            logger.warning("chiamata a Claude fallita: %s", type(exc).__name__)
            raise ClaudeClientError(type(exc).__name__) from exc
        content = [_normalize(block) for block in message.content]
        raw = [_block_to_raw(block) for block in message.content]
        return ClaudeResponse(content=content, stop_reason=message.stop_reason, raw_content=raw)


def _model_options(model: str) -> dict[str, Any]:
    """Opzioni per modello: la chat non ha bisogno di ragionamento esteso.

    Su Sonnet 5.5 ``between_tools`` spegne il ragionamento visibile e ``effort`` basso tiene
    brevi le risposte; Haiku 4.5 non accetta ``effort``.
    """
    if model.startswith("claude-sonnet-5"):
        return {"thinking": {"type": "between_tools"}, "output_config": {"effort": "low"}}
    return {}


def _normalize(block: Any) -> ContentBlock:
    """Riduce un blocco dell'SDK ai campi che servono all'agente."""
    if block.type == "text":
        return ContentBlock(type="text", text=str(block.text))
    if block.type == "tool_use":
        tool_input = block.input if isinstance(block.input, dict) else {}
        return ContentBlock(
            type="tool_use", id=str(block.id), name=str(block.name), input=dict(tool_input)
        )
    return ContentBlock(type=str(block.type))
