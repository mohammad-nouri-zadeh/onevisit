"""Webhook SMS, link di risposta delle email, pagina demo (C6, C7, B6, B9)."""

import logging
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from gateway.deps import GatewayDeps
from gateway.main import create_app
from onevisit_channels import PURPOSE_REPLY, twilio_signature

from .conftest import PHONE, FakeStore

SECRET_TEXT = "il mio codice RSSMRA80A01F205X"


def _client(deps: GatewayDeps) -> TestClient:
    return TestClient(create_app(deps=deps))


def test_stop_revokes_consents_and_sends_confirmation_last(
    make_deps: Callable[..., GatewayDeps], fake_store: FakeStore
) -> None:
    deps = make_deps()
    client = _client(deps)

    response = client.post(
        "/sms/inbound", data={"From": PHONE, "Body": " Stop ", "MessageSid": "SM1"}
    )

    assert response.status_code == 200
    assert fake_store.target is not None
    assert fake_store.revoked == [fake_store.target.contact_id]
    assert fake_store.revoked_phones == [fake_store.phone_digest]
    assert all(v is None for v in fake_store.target.consents.values())
    assert deps.fake_sms is not None
    last = deps.fake_sms.sent[-1]
    assert last.to == PHONE
    assert "consensi revocati" in last.body.lower()


def test_reply_digit_records_outcome(
    make_deps: Callable[..., GatewayDeps], fake_store: FakeStore
) -> None:
    deps = make_deps()

    _client(deps).post("/sms/inbound", data={"From": PHONE, "Body": "2", "MessageSid": "SM2"})

    assert fake_store.outcomes == [(fake_store.case_id, "missing")]


def test_duplicate_message_sid_is_processed_once(
    make_deps: Callable[..., GatewayDeps], fake_store: FakeStore
) -> None:
    client = _client(make_deps())

    for _ in range(2):
        client.post("/sms/inbound", data={"From": PHONE, "Body": "1", "MessageSid": "SM3"})

    assert fake_store.outcomes == [(fake_store.case_id, "ok")]


def test_free_text_gets_link_and_is_never_logged(
    make_deps: Callable[..., GatewayDeps], fake_store: FakeStore, caplog: pytest.LogCaptureFixture
) -> None:
    deps = make_deps()
    caplog.set_level(logging.DEBUG)

    _client(deps).post(
        "/sms/inbound", data={"From": PHONE, "Body": SECRET_TEXT, "MessageSid": "SM4"}
    )

    assert deps.fake_sms is not None
    assert "http://assistant.test/c/" in deps.fake_sms.sent[-1].body
    assert SECRET_TEXT not in caplog.text
    assert PHONE not in caplog.text
    assert fake_store.outcomes == []


def test_bad_signature_is_rejected_without_content_in_logs(
    make_deps: Callable[..., GatewayDeps], fake_store: FakeStore, caplog: pytest.LogCaptureFixture
) -> None:
    deps = make_deps(sms_provider="twilio", twilio_account_sid="AC000", twilio_auth_token="tok")
    caplog.set_level(logging.DEBUG)
    data = {"From": PHONE, "Body": SECRET_TEXT, "MessageSid": "SM5"}

    response = _client(deps).post(
        "/sms/inbound", data=data, headers={"X-Twilio-Signature": "forged"}
    )

    assert response.status_code == 403
    assert SECRET_TEXT not in caplog.text
    assert PHONE not in caplog.text
    assert fake_store.outcomes == []


def test_good_signature_is_accepted(
    make_deps: Callable[..., GatewayDeps], fake_store: FakeStore
) -> None:
    deps = make_deps(
        sms_provider="twilio",
        twilio_account_sid="AC000",
        twilio_auth_token="tok",
        gateway_base_url="https://gateway.example.org",
    )
    data = {"From": PHONE, "Body": "3", "MessageSid": "SM6"}
    signature = twilio_signature("tok", "https://gateway.example.org/sms/inbound", data)

    response = _client(deps).post(
        "/sms/inbound", data=data, headers={"X-Twilio-Signature": signature}
    )

    assert response.status_code == 200
    assert fake_store.outcomes == [(fake_store.case_id, "other")]


def test_reply_link_records_outcome_and_thanks(
    make_deps: Callable[..., GatewayDeps], fake_store: FakeStore
) -> None:
    deps = make_deps()
    assert fake_store.target is not None
    token = deps.signer.sign(PURPOSE_REPLY, fake_store.case_id, fake_store.target.contact_id)

    response = _client(deps).get(f"/r/{token}?choice=1", headers={"Accept-Language": "it-IT"})

    assert response.status_code == 200
    assert "Grazie" in response.text
    assert "http://assistant.test/o/" in response.text
    assert fake_store.outcomes == [(fake_store.case_id, "ok")]


def test_tampered_reply_link_is_rejected(
    make_deps: Callable[..., GatewayDeps], fake_store: FakeStore
) -> None:
    response = _client(make_deps()).get("/r/not-a-token?choice=1")

    assert response.status_code == 400
    assert fake_store.outcomes == []


def test_demo_phone_shows_masked_messages(
    make_deps: Callable[..., GatewayDeps], fake_store: FakeStore
) -> None:
    deps = make_deps(environment="development")
    client = _client(deps)
    client.post("/sms/inbound", data={"From": PHONE, "Body": "aiuto", "MessageSid": "SM7"})

    page = client.get("/demo/phone")

    assert page.status_code == 200
    assert "intelligenza artificiale" in page.text
    assert PHONE not in page.text


def test_demo_phone_is_hidden_in_production(make_deps: Callable[..., GatewayDeps]) -> None:
    response = _client(make_deps(environment="production")).get("/demo/phone")

    assert response.status_code == 404
