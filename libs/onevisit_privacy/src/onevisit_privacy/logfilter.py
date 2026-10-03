"""Filtro di logging che toglie i dati personali da ogni messaggio (storia C9)."""

import logging

from onevisit_privacy.redact import redact


class PiiLogFilter(logging.Filter):
    """Passa ogni messaggio (e il testo dell'eccezione) da :func:`redact`."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage()).text
        record.args = None
        if record.exc_text:
            record.exc_text = redact(record.exc_text).text
        return True
