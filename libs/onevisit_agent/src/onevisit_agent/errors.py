"""Eccezioni della libreria dell'agente (storia C3).

I messaggi delle eccezioni non contengono mai testo del cittadino: solo codici e id opachi.
"""


class AgentError(Exception):
    """Base comune delle eccezioni di ``onevisit_agent``."""


class ClaudeClientError(AgentError):
    """Il modello non ha risposto: errore di rete, timeout o errore dell'API."""


class ToolInputError(AgentError):
    """Un argomento passato da Claude a uno strumento non è valido."""
