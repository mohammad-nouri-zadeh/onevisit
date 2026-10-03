"""L'agente OneVisit: ciclo di un turno con strumenti, validazione e ripiego (storie C3, B1-B4).

``Agent.run_turn`` non dipende dal canale: riceve lo stato della sessione, il messaggio e le
capacità del canale, e restituisce messaggi, risposte rapide, lingua, stato aggiornato ed eventi.
Nei log finiscono solo nomi di strumenti e codici di motivo, mai il testo dei messaggi.
"""

import json
import logging
from functools import cache
from importlib import resources
from typing import Any

from onevisit_agent.catalog_view import CatalogView
from onevisit_agent.client import ClaudeClient
from onevisit_agent.errors import AgentError, ClaudeClientError
from onevisit_agent.language import initial_language, parse_reply
from onevisit_agent.models import AgentConfig, Capabilities, SessionState, TurnResult
from onevisit_agent.tool_schemas import tool_definitions
from onevisit_agent.tools import ToolRunner
from onevisit_agent.validator import validate_reply

logger = logging.getLogger(__name__)

# Istruzione interna (non rivolta al cittadino) per la rigenerazione dopo un blocco.
_REGENERATE_NOTE = (
    "<validator>Your previous reply was blocked for: {reasons}. Rewrite it following the "
    "system rules: cite every fact as [fonte: <source_id>] using only source_ids from tool "
    "results, never use eligibility words, start with the <lang> marker.</validator>"
)
_CHANNEL_NOTE = "<channel>{channel}; max {max_chars} characters</channel>"


class _ToolLoopError(AgentError):
    """Il modello ha superato il numero massimo di giri con gli strumenti."""


@cache
def load_system_prompt() -> str:
    """Il prompt di sistema versionato, letto dal pacchetto."""
    return resources.files("onevisit_agent").joinpath("prompts/system.md").read_text("utf-8")


@cache
def _messages() -> dict[str, dict[str, str]]:
    raw = resources.files("onevisit_agent").joinpath("messages.json").read_text("utf-8")
    data: dict[str, dict[str, str]] = json.loads(raw)
    return data


def fallback_message(language: str, url: str) -> str:
    """Messaggio di cortesia con il link ufficiale (italiano per ``it``, inglese altrimenti)."""
    texts = _messages()["fallback"]
    return texts["it" if language == "it" else "en"].format(url=url)


def catalog_index(catalog: CatalogView, config: AgentConfig) -> str:
    """Indice del catalogo per il blocco di sistema in cache: servizi e domande decisive."""
    services: list[dict[str, Any]] = []
    for summary in catalog.services():
        service = catalog.service(summary.id)
        questions = (
            [{"id": q.id, "options": list(q.options)} for q in service.deciding_questions]
            if service
            else []
        )
        services.append(
            {
                "id": summary.id,
                "title_it": summary.title_it,
                "title_en": summary.title_en,
                "deciding_questions": questions,
            }
        )
    index = json.dumps(services, ensure_ascii=False, sort_keys=True)
    return (
        f"# Catalog index\n\nToday's date: {config.today.isoformat()}\n"
        f"City website (fallback): {config.official_fallback_url}\n\n"
        f"Services in the catalog (anything else is not covered):\n{index}\n"
    )


class Agent:
    """Agente conversazionale sopra un ``ClaudeClient`` e un catalogo."""

    def __init__(self, *, client: ClaudeClient, catalog: CatalogView, config: AgentConfig) -> None:
        self.client = client
        self.catalog = catalog
        self.config = config
        self._known_sources = catalog.source_ids()
        self._tools = tool_definitions()
        self._system: list[dict[str, Any]] = [
            {"type": "text", "text": load_system_prompt()},
            {
                "type": "text",
                "text": catalog_index(catalog, config),
                "cache_control": {"type": "ephemeral"},
            },
        ]

    def run_turn(self, state: SessionState, message: str, capabilities: Capabilities) -> TurnResult:
        """Esegue un turno completo. Non solleva eccezioni per errori del modello."""
        state = state.model_copy(deep=True)
        if not state.history and capabilities.browser_language:
            state.language = initial_language(capabilities.browser_language)
        previous_history = list(state.history)
        messages = [*previous_history, self._user_message(message, capabilities)]
        runner = ToolRunner(catalog=self.catalog, config=self.config, case=state.case)
        try:
            raw_reply = self._answer(messages, runner)
        except (ClaudeClientError, _ToolLoopError) as exc:
            logger.warning("turno senza risposta: %s", type(exc).__name__)
            return self._fallback(state, messages[: len(previous_history) + 1], runner, False)
        if raw_reply is None:
            return self._fallback(state, messages[: len(previous_history) + 1], runner, True)
        parsed = parse_reply(raw_reply)
        if parsed.language and parsed.language.isalpha():
            state.language = parsed.language
        state.history = messages
        return TurnResult(
            messages=[parsed.text],
            quick_replies=parsed.quick_replies if capabilities.buttons else [],
            language=state.language,
            state=state,
            blocked=False,
            events=runner.events,
        )

    def _answer(self, messages: list[dict[str, Any]], runner: ToolRunner) -> str | None:
        """Risposta validata; una rigenerazione; ``None`` se resta bloccata."""
        reply = self._complete(messages, runner)
        reasons = self._validate(reply, runner)
        if not reasons:
            return reply
        logger.info("risposta bloccata, rigenero: %s", ",".join(reasons))
        note = _REGENERATE_NOTE.format(reasons="; ".join(reasons))
        messages.append({"role": "user", "content": [{"type": "text", "text": note}]})
        reply = self._complete(messages, runner)
        reasons = self._validate(reply, runner)
        if not reasons:
            return reply
        logger.info("risposta bloccata due volte: %s", ",".join(reasons))
        return None

    def _validate(self, reply: str, runner: ToolRunner) -> list[str]:
        text = parse_reply(reply).text
        return validate_reply(
            text, known_source_ids=self._known_sources, used_facts=runner.used_facts
        )

    def _complete(self, messages: list[dict[str, Any]], runner: ToolRunner) -> str:
        """Ciclo strumento -> risposta fino al testo finale; aggiunge tutto a ``messages``."""
        for _round in range(self.config.max_tool_rounds):
            response = self.client.create(
                model=self.config.model_conversation,
                max_tokens=self.config.max_tokens,
                system=self._system,
                messages=messages,
                tools=self._tools,
            )
            messages.append({"role": "assistant", "content": response.raw_content})
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                return "".join(b.text for b in response.content if b.type == "text")
            results: list[dict[str, Any]] = []
            for block in tool_uses:
                content, is_error = runner.run(block.name, block.input)
                logger.info("strumento %s eseguito (errore=%s)", block.name, is_error)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": results})
        raise _ToolLoopError("max_tool_rounds")

    def _user_message(self, message: str, capabilities: Capabilities) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": message}]
        if capabilities.max_chars:
            note = _CHANNEL_NOTE.format(
                channel=capabilities.channel, max_chars=capabilities.max_chars
            )
            content.append({"type": "text", "text": note})
        return {"role": "user", "content": content}

    def _fallback(
        self,
        state: SessionState,
        base_messages: list[dict[str, Any]],
        runner: ToolRunner,
        blocked: bool,
    ) -> TurnResult:
        text = fallback_message(state.language, self.config.official_fallback_url)
        state.history = [
            *base_messages,
            {"role": "assistant", "content": [{"type": "text", "text": text}]},
        ]
        return TurnResult(
            messages=[text],
            language=state.language,
            state=state,
            blocked=blocked,
            events=runner.events,
        )
