"""Contatto (B5), checklist (B7), esito (B8), consensi (B9), errori senza traccia."""

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from onevisit_agent.testing import FakeClaudeClient, text_response, tool_response
from onevisit_channels import PURPOSE_CHECKLIST, PURPOSE_CONSENTS, PURPOSE_OUTCOME, LinkSigner

FORBIDDEN = ("idoneo", "in regola", "garantito", "eligible", "guaranteed")
FINAL_IT = "In base alle fonti citate risultano presenti tutti i documenti richiesti."
FINAL_EN = "According to the cited sources, all the required documents are present."
SIGNER = LinkSigner("test-link-key")
ANSWERS = {
    "residenza": "milano",
    "motivo": "rinnovo",
    "eta": "adulto",
    "cittadinanza": "extra-ue",
    "presenza": "sportello",
}
FAKE_EMAIL = "persona.finta@example.org"


def _with_appointment(make_client: Callable[..., TestClient]) -> TestClient:
    fake = FakeClaudeClient(
        script=[
            tool_response(
                ("identify_case", {"service_id": "carta-identita", "confirmed": True}),
                ("record_appointment", {"date": date(2030, 1, 15).isoformat(), "time": "09:00"}),
            ),
            text_response("Fatto [fonte: ds549]\n<lang>it</lang>"),
        ]
    )
    client = make_client(fake)
    client.post("/chat", data={"message": "Ho appuntamento"})
    return client


def test_email_contact_is_encrypted_and_only_confirmation_is_scheduled(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = _with_appointment(make_client)

    response = client.post(
        "/contact", data={"choice": "email", "email": FAKE_EMAIL, "consent_reminder": "1"}
    )

    assert response.status_code == 200
    contact = next(kw for name, kw in fake_repo.calls if name == "create_contact")
    assert FAKE_EMAIL.encode() not in contact["email_enc"]
    assert contact["consents"]["followup"] is None
    kinds = [kw["kind"] for name, kw in fake_repo.calls if name == "schedule_notification"]
    assert kinds == ["email_confirm"]


def test_confirm_link_schedules_consented_notifications(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = _with_appointment(make_client)
    client.post("/contact", data={"choice": "email", "email": FAKE_EMAIL, "consent_reminder": "1"})
    contact_id = next(iter(fake_repo.contacts))
    case_id = next(kw["case_id"] for name, kw in fake_repo.calls if name == "link_contact")
    token = SIGNER.sign("email_confirm", case_id, contact_id)

    response = client.get(f"/confirm/{token}")

    assert response.status_code == 200
    kinds = [kw["kind"] for name, kw in fake_repo.calls if name == "schedule_notification"]
    assert kinds == ["email_confirm", "reminder"]


def test_invalid_email_is_rejected(make_client: Callable[..., TestClient]) -> None:
    client = _with_appointment(make_client)

    response = client.post("/contact", data={"choice": "email", "email": "not-an-email"})

    assert response.status_code == 422
    assert "not-an-email" not in response.text


def test_sms_contact_is_normalised_and_scheduled_directly(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = _with_appointment(make_client)

    client.post(
        "/contact", data={"choice": "sms", "phone": "333 000 0000", "consent_followup": "1"}
    )

    contact = next(kw for name, kw in fake_repo.calls if name == "create_contact")
    assert contact["preferred_channel"] == "sms" and contact["phone_enc"]
    kinds = [kw["kind"] for name, kw in fake_repo.calls if name == "schedule_notification"]
    assert kinds == ["followup", "followup_nudge"]


def test_checklist_final_sentence_in_italian_and_english(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = make_client()
    pages = {}
    for language in ("it", "en"):
        case_id = fake_repo.add_case("carta-identita", language, ANSWERS)
        token = SIGNER.sign(PURPOSE_CHECKLIST, case_id)
        ids = client.get(f"/c/{token}").text.split('name="have" value="')[1:]
        have = [chunk.split('"')[0] for chunk in ids]

        pages[language] = client.post(f"/c/{token}", data={"have": have}).text

    assert FINAL_IT in pages["it"] and FINAL_EN in pages["en"]
    for text in pages.values():
        assert not any(word in text.lower() for word in FORBIDDEN)


def test_checklist_lists_what_is_missing(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = make_client()
    token = SIGNER.sign(PURPOSE_CHECKLIST, fake_repo.add_case("carta-identita", "it", ANSWERS))

    response = client.post(f"/c/{token}", data={})

    assert "Ti manca ancora" in response.text
    assert FINAL_IT not in response.text


def test_outcome_free_text_is_not_stored(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = make_client()
    case_id = fake_repo.add_case("carta-identita", "it", ANSWERS)
    token = SIGNER.sign(PURPOSE_OUTCOME, case_id)
    secret_text = "Mancava la ricevuta, chiamatemi al 333 000 0000 RSSMRA80A01F205X"

    response = client.post(
        f"/o/{token}",
        data={"outcome": "missing", "missing_text": secret_text, "rating": "4"},
    )

    assert response.status_code == 200
    outcome = next(kw for name, kw in fake_repo.calls if name == "record_outcome")
    assert outcome["outcome"] == "missing" and outcome["rating"] == 4
    assert secret_text not in repr(fake_repo.calls)
    assert "RSSMRA80A01F205X" not in repr(fake_repo.calls)


def test_consents_can_be_revoked_and_contact_deleted(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = _with_appointment(make_client)
    client.post("/contact", data={"choice": "email", "email": FAKE_EMAIL, "consent_reminder": "1"})
    contact_id = next(iter(fake_repo.contacts))
    case_id = next(kw["case_id"] for name, kw in fake_repo.calls if name == "link_contact")
    token = SIGNER.sign(PURPOSE_CONSENTS, case_id, contact_id)

    page = client.get(f"/consents/{token}")
    client.post(f"/consents/{token}", data={"action": "revoke"})
    client.post(f"/consents/{token}", data={"action": "delete"})

    assert page.status_code == 200
    assert {"revoke_consents", "delete_contact"} <= set(fake_repo.names())


def test_bad_token_returns_friendly_error(make_client: Callable[..., TestClient]) -> None:
    client = make_client()

    response = client.get("/c/not-a-real-token")

    assert response.status_code == 404
    assert "Traceback" not in response.text


def test_agent_crash_does_not_leak_user_text_or_traceback(
    make_client: Callable[..., TestClient],
) -> None:
    fake = FakeClaudeClient(script=[RuntimeError("boom")])
    client = make_client(fake)

    response = client.post("/chat", data={"message": "testo segreto del cittadino"})

    assert "Traceback" not in response.text
    assert "boom" not in response.text


def test_contact_without_any_consent_is_not_stored(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = _with_appointment(make_client)

    response = client.post("/contact", data={"choice": "email", "email": FAKE_EMAIL})

    assert response.status_code == 200
    assert "create_contact" not in fake_repo.names()
    assert "schedule_notification" not in fake_repo.names()


def test_contact_posted_twice_replaces_the_previous_contact(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = _with_appointment(make_client)
    data = {"choice": "sms", "phone": "333 000 0000", "consent_reminder": "1"}

    client.post("/contact", data=data)
    first = next(iter(fake_repo.contacts))
    client.post("/contact", data=data)

    deleted = [kw["contact_id"] for name, kw in fake_repo.calls if name == "delete_contact"]
    assert deleted == [first]


def test_contact_sets_the_appointment_week_on_the_case(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = _with_appointment(make_client)

    client.post(
        "/contact", data={"choice": "sms", "phone": "333 000 0000", "consent_followup": "1"}
    )

    weeks = [kw.get("appointment_week") for name, kw in fake_repo.calls if name == "update_case"]
    assert date(2030, 1, 14) in weeks


def test_both_with_sms_primary_asks_to_confirm_the_backup_email(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = _with_appointment(make_client)

    client.post(
        "/contact",
        data={
            "choice": "both",
            "primary": "sms",
            "email": FAKE_EMAIL,
            "phone": "333 000 0000",
            "consent_reminder": "1",
        },
    )

    kinds = [kw["kind"] for name, kw in fake_repo.calls if name == "schedule_notification"]
    assert kinds[0] == "email_confirm" and "reminder" in kinds
