"""Test del passaggio deterministico (storia C9) sull'insieme di frasi sintetiche."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from onevisit_privacy import contains_pii, redact

CORPUS: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).parent / "fixtures" / "pii_corpus.yaml").read_text(encoding="utf-8")
)


def test_corpus_has_at_least_twenty_sentences() -> None:
    assert len(CORPUS) >= 20


@pytest.mark.parametrize("entry", CORPUS, ids=[str(i) for i in range(len(CORPUS))])
def test_no_value_survives_redaction(entry: dict[str, Any]) -> None:
    result = redact(entry["text"])

    for value in entry["values"]:
        assert value not in result.text
        assert value.replace(" ", "") not in result.text.replace(" ", "")
    assert set(entry["categories"]) <= set(result.found)
    assert contains_pii(entry["text"])
    assert not contains_pii(result.text)


@pytest.mark.parametrize(
    "text",
    [
        "Appuntamento alle 10:30 del 03/10/2026.",
        "Ci vediamo il 2026-10-03 alle 9.45.",
        "Il permesso di soggiorno scade il 03.10.2026.",
        "Servono 2 foto e 16,00 euro di marca da bollo.",
        "Via Larga 12, sportello 4, municipio 1.",
        "Nel 2024 sono arrivato in Italia.",
    ],
)
def test_dates_times_and_plain_numbers_are_kept(text: str) -> None:
    result = redact(text)

    assert result.text == text
    assert result.found == []


def test_placeholders_are_used() -> None:
    result = redact("a@example.org RSSMRA80A01F205X +39 333 000 0000")

    assert result.text == "[EMAIL] [CODICE_FISCALE] [TELEFONO]"
