"""Eccezioni della libreria privacy (storia C9).

I messaggi non contengono mai valori personali, chiavi o testi del cittadino.
"""


class PrivacyError(Exception):
    """Errore base della libreria ``onevisit_privacy``."""


class InvalidKeyError(PrivacyError):
    """Una chiave non e' base64 valido o non e' lunga 32 byte."""


class ClaudeUnavailableError(PrivacyError):
    """L'API di Claude non ha risposto (chiave, 429, 5xx, timeout): si usa la riserva."""


class DecryptionError(PrivacyError):
    """Il testo cifrato e' corrotto o la chiave non corrisponde."""
