"""Eccezioni della libreria database (storia C2). Messaggi senza valori personali."""


class DbError(Exception):
    """Errore base di ``onevisit_db``."""


class NotFoundError(DbError):
    """L'oggetto richiesto non esiste (il messaggio contiene solo il tipo)."""


class InvalidFieldError(DbError):
    """Un campo non e' modificabile o un valore non e' ammesso."""
