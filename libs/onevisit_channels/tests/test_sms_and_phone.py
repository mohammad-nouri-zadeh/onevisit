"""Risposte SMS, numeri E.164, firma Twilio, fornitori finti (C6, B6)."""

import httpx
import pytest

from onevisit_channels import (
    ChannelSendError,
    FakeSmsProvider,
    TwilioSmsProvider,
    normalize_phone,
    parse_sms_reply,
    twilio_signature,
    validate_twilio_signature,
)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("stop", "STOP"),
        (" Stop ", "STOP"),
        ("STOP.", "STOP"),
        ("aiuto", "AIUTO"),
        ("HELP", "AIUTO"),
        ("2", "2"),
        (" 1 ", "1"),
        ("3\n", "3"),
        ("ciao, ho una domanda", "other"),
        ("", "other"),
    ],
)
def test_parse_sms_reply(text: str, kind: str) -> None:
    assert parse_sms_reply(text).kind == kind


@pytest.mark.parametrize("raw", ["333 000 0000", "+39 333 000 0000", "0039 3330000000"])
def test_normalize_phone_to_e164(raw: str) -> None:
    assert normalize_phone(raw) == "+393330000000"


def test_normalize_phone_rejects_garbage_without_echoing_it() -> None:
    with pytest.raises(ValueError) as info:
        normalize_phone("abc")

    assert "abc" not in str(info.value)


def test_twilio_signature_matches_documented_example() -> None:
    # Esempio pubblico della documentazione Twilio sulla sicurezza dei webhook.
    url = "https://example.com/myapp.php?foo=1&bar=2"
    params = {
        "CallSid": "CA1234567890ABCDE",
        "Caller": "+12349013030",
        "Digits": "1234",
        "From": "+12349013030",
        "To": "+18005551212",
    }
    token = "12345"

    signature = twilio_signature(token, url, params)

    assert validate_twilio_signature(token, url, params, signature)
    assert not validate_twilio_signature(token, url, params, "bad")
    assert not validate_twilio_signature(token, url, params, None)


async def test_fake_provider_records_and_simulates_failures() -> None:
    provider = FakeSmsProvider(fail_times=1)

    with pytest.raises(ChannelSendError):
        await provider.send("+393330000000", "ciao")
    await provider.send("+393330000000", "ciao")

    assert [sms.body for sms in provider.sent] == ["ciao"]


async def test_twilio_provider_posts_form_with_basic_auth() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"sid": "SM123"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = TwilioSmsProvider(
        account_sid="AC000", auth_token="tok", from_number="+15005550006", client=client
    )

    sid = await provider.send("+393330000000", "ciao")

    assert sid == "SM123"
    assert seen[0].url.path.endswith("/Accounts/AC000/Messages.json")
    assert seen[0].headers["authorization"].startswith("Basic ")


async def test_twilio_provider_error_does_not_leak_number() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(400)))
    provider = TwilioSmsProvider(
        account_sid="AC000", auth_token="tok", from_number="+15005550006", client=client
    )

    with pytest.raises(ChannelSendError) as info:
        await provider.send("+393330000000", "ciao")

    assert "3330000000" not in str(info.value)
