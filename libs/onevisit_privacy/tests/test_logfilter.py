"""Il filtro di logging toglie email e telefoni dai messaggi (storia C9)."""

import logging

import pytest

from onevisit_privacy import PiiLogFilter


def test_filter_scrubs_message_and_args(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("onevisit_privacy.test")
    log_filter = PiiLogFilter()
    logger.addFilter(log_filter)
    try:
        with caplog.at_level(logging.INFO, logger="onevisit_privacy.test"):
            logger.info("contatto %s tel %s", "utente@example.org", "+39 333 000 0000")
    finally:
        logger.removeFilter(log_filter)

    assert "utente@example.org" not in caplog.text
    assert "333 000 0000" not in caplog.text
    assert "[EMAIL]" in caplog.text
    assert "[TELEFONO]" in caplog.text


def test_filter_on_a_bare_record() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "cf %s", ("RSSMRA80A01F205X",), None)

    assert PiiLogFilter().filter(record)
    assert record.getMessage() == "cf [CODICE_FISCALE]"
