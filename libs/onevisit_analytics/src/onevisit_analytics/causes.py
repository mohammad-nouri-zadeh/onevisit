"""Le sei cause degli esiti negativi (storia C10).

``onevisit-privacy`` definisce lo stesso elenco (docs/contracts.md sezione 2), ma non e'
una dipendenza dichiarata di ``onevisit-analytics``: qui c'e' una copia locale con gli
stessi sei identificativi. Se l'elenco cambia, va cambiato in entrambi i pacchetti.
"""

from enum import StrEnum


class Cause(StrEnum):
    """Causa di un esito negativo allo sportello."""

    PAGINA_INCOMPLETA = "pagina-incompleta"
    PROCEDURA_NON_AGGIORNATA = "procedura-non-aggiornata"
    PROCEDURA_MANCANTE = "procedura-mancante"
    ENTE_O_UFFICIO_SBAGLIATO = "ente-o-ufficio-sbagliato"
    PAGINA_CHIARA_NON_SEGUITA = "pagina-chiara-non-seguita"
    RICHIESTA_NON_PREVISTA = "richiesta-non-prevista"


CAUSES: tuple[str, ...] = tuple(c.value for c in Cause)

# Destinatario della lacuna per causa, quando la fonte e' comunale (C10).
RECIPIENT_BY_CAUSE: dict[Cause, str] = {
    Cause.PAGINA_INCOMPLETA: "redazione",
    Cause.PROCEDURA_NON_AGGIORNATA: "redazione",
    Cause.PROCEDURA_MANCANTE: "redazione",
    Cause.ENTE_O_UFFICIO_SBAGLIATO: "ufficio",
    Cause.PAGINA_CHIARA_NON_SEGUITA: "assistente",
    Cause.RICHIESTA_NON_PREVISTA: "ufficio",
}

RECIPIENTS: tuple[str, ...] = ("redazione", "ufficio", "ente-nazionale", "assistente")
