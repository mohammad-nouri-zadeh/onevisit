"""Modelli dei messaggi: mai il nome del servizio, SMS entro due segmenti GSM-7 (C6, C7, B7)."""

import json
from pathlib import Path

import pytest

from onevisit_channels import (
    MESSAGE_KINDS,
    SMS_MAX_CHARS,
    is_gsm7,
    render_notification,
    sms_segments,
)
from onevisit_channels.render import TEMPLATES_DIR

REPO_ROOT = Path(__file__).resolve().parents[3]
LINK = "https://onevisit.example.org/c/" + "x" * 90
CONSENTS = "https://onevisit.example.org/consents/" + "y" * 90


def _service_terms() -> list[str]:
    terms: list[str] = []
    for path in (REPO_ROOT / "data" / "services").glob("*.json"):
        service = json.loads(path.read_text(encoding="utf-8"))
        terms.append(service["id"].lower())
        terms.extend(title.lower() for title in service["title"].values())
    return terms


def test_service_titles_are_available() -> None:
    assert _service_terms(), "nessun servizio trovato in data/services"


@pytest.mark.parametrize("path", sorted(TEMPLATES_DIR.rglob("*.*")), ids=lambda p: p.name)
def test_no_template_names_a_service(path: Path) -> None:
    content = path.read_text(encoding="utf-8").lower()

    for term in _service_terms():
        assert term not in content


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("kind", MESSAGE_KINDS)
@pytest.mark.parametrize("days_left", [None, 0, 1, 3, 30])
def test_sms_fits_two_gsm7_segments(kind: str, language: str, days_left: int | None) -> None:
    message = render_notification(
        kind, language=language, channel="sms", days_left=days_left, link=LINK
    )

    assert is_gsm7(message.text)
    assert len(message.text) <= SMS_MAX_CHARS
    assert sms_segments(message.text) <= 2
    assert LINK in message.text
    assert "{" not in message.text


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("kind", MESSAGE_KINDS)
def test_email_has_subject_text_html_and_consents_link(kind: str, language: str) -> None:
    message = render_notification(
        kind, language=language, channel="email", days_left=3, link=LINK, consents_link=CONSENTS
    )

    assert message.subject and message.subject.startswith("OneVisit")
    assert message.html is not None
    assert CONSENTS in message.text
    assert CONSENTS in message.html


def test_unknown_language_falls_back_to_english() -> None:
    message = render_notification("reminder", language="ar", channel="sms", days_left=3, link=LINK)

    assert "in 3 days" in message.text


def test_followup_email_has_three_signed_reply_links() -> None:
    message = render_notification(
        "followup",
        language="it",
        channel="email",
        days_left=None,
        link=LINK,
        consents_link=CONSENTS,
    )

    for choice in ("1", "2", "3"):
        assert f"{LINK}?choice={choice}" in message.text
