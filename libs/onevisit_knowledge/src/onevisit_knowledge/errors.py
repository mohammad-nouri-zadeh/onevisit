"""Eccezioni della libreria della conoscenza (storie A1, A2, C4).

I messaggi contengono solo identificativi di servizi, fonti e file: mai dati personali.
"""


class KnowledgeError(Exception):
    """Errore generico della base di conoscenza."""


class CatalogError(KnowledgeError):
    """Il catalogo non si carica (file mancante, JSON non valido) o un servizio non esiste."""
