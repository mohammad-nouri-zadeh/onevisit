"""Agente Claude di OneVisit: prompt, strumenti, validazione delle risposte (storie C3, B1-B4).

Interfaccia pubblica fissata in docs/contracts.md, sezione 3.
"""

from onevisit_agent.agent import Agent, fallback_message, load_system_prompt
from onevisit_agent.catalog_view import CatalogView
from onevisit_agent.client import AnthropicClaudeClient, ClaudeClient, ClaudeResponse, ContentBlock
from onevisit_agent.errors import AgentError, ClaudeClientError, ToolInputError
from onevisit_agent.models import (
    AgentConfig,
    AgentEvent,
    AppointmentInfo,
    Capabilities,
    CaseState,
    SessionState,
    TurnResult,
)
from onevisit_agent.validator import validate_reply

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentError",
    "AgentEvent",
    "AnthropicClaudeClient",
    "AppointmentInfo",
    "Capabilities",
    "CaseState",
    "CatalogView",
    "ClaudeClient",
    "ClaudeClientError",
    "ClaudeResponse",
    "ContentBlock",
    "SessionState",
    "ToolInputError",
    "TurnResult",
    "fallback_message",
    "load_system_prompt",
    "validate_reply",
]
