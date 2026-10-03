"""Client Claude finto per i test (storia C3, docs/testing-strategy.md).

``FakeClaudeClient`` restituisce risposte preparate in ordine (testo e chiamate agli strumenti)
e registra le chiamate ricevute. Una voce del copione può essere un'eccezione da sollevare.
"""

import copy
import itertools
from dataclasses import dataclass, field
from typing import Any

from onevisit_agent.client import ClaudeResponse, ContentBlock
from onevisit_agent.errors import ClaudeClientError

_ids = itertools.count(1)


def text_response(text: str) -> ClaudeResponse:
    """Risposta finale di solo testo."""
    return ClaudeResponse(
        content=[ContentBlock(type="text", text=text)],
        stop_reason="end_turn",
        raw_content=[{"type": "text", "text": text}],
    )


def tool_response(*calls: tuple[str, dict[str, Any]], text: str = "") -> ClaudeResponse:
    """Risposta con una o più chiamate a strumenti (nome, argomenti)."""
    blocks: list[ContentBlock] = [ContentBlock(type="text", text=text)] if text else []
    for name, tool_input in calls:
        blocks.append(
            ContentBlock(
                type="tool_use", id=f"toolu_fake_{next(_ids)}", name=name, input=dict(tool_input)
            )
        )
    raw: list[dict[str, Any]] = []
    for block in blocks:
        if block.type == "text":
            raw.append({"type": "text", "text": block.text})
        else:
            raw.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input)}
            )
    return ClaudeResponse(content=blocks, stop_reason="tool_use", raw_content=raw)


@dataclass
class RecordedCall:
    """Una chiamata ricevuta dal client finto (copia degli argomenti)."""

    model: str
    system: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None


@dataclass
class FakeClaudeClient:
    """Client finto: consuma il copione in ordine; se finisce solleva ``ClaudeClientError``."""

    script: list[ClaudeResponse | Exception] = field(default_factory=list)
    calls: list[RecordedCall] = field(default_factory=list)

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ClaudeResponse:
        """Registra la chiamata e restituisce la prossima risposta del copione."""
        del max_tokens
        self.calls.append(
            RecordedCall(model=model, system=system, messages=copy.deepcopy(messages), tools=tools)
        )
        if not self.script:
            raise ClaudeClientError("script_exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
