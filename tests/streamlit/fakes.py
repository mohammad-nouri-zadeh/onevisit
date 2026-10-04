"""A fake Anthropic client: replays scripted responses, never touches the network."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field


@dataclass
class Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class Response:
    content: list
    stop_reason: str = "end_turn"
    usage: Usage | None = None


def text(t: str) -> Response:
    return Response([Block("text", text=t)])


_ids = itertools.count(1)


def tool(name: str, **args) -> Response:
    return Response(
        [Block("tool_use", id=f"toolu_{next(_ids)}", name=name, input=args)], stop_reason="tool_use"
    )


class FakeClient:
    """client.beta.messages.create(...) returns the next scripted response and records the call."""

    def __init__(self, responses: list[Response]):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.beta = self
        self.messages = self

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs.get("messages", []))})
        if not self.responses:
            raise AssertionError("FakeClient ran out of scripted responses")
        return self.responses.pop(0)
