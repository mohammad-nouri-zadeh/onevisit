"""Eccezioni della libreria di analisi (storie C10, C11, D1). Messaggi senza dati personali."""


class AnalyticsError(Exception):
    """Errore base di ``onevisit_analytics``."""


class ProperNameError(AnalyticsError):
    """Un campo da salvare contiene una parola che sembra un nome proprio (C10)."""


class ClaudeOutputError(AnalyticsError):
    """Risposta di Claude non valida o API non raggiungibile; si usa la regola di riserva."""
