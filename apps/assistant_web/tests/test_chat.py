"""Chat del cittadino: benvenuto, turno con citazione, redazione, eventi (B1-B4)."""

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from onevisit_agent.testing import FakeClaudeClient, text_response, tool_response

FAKE_CF = "RSSMRA80A01F205X"
FAKE_EMAIL = "mario.test@example.org"
# Data futura fissa per gli appuntamenti finti.
FUTURE_DAY = date(2030, 1, 15)


def test_welcome_is_italian_by_default(make_client: Callable[..., TestClient]) -> None:
    client = make_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "Ti aiuto a preparare" in response.text
    assert 'aria-live="polite"' in response.text
    assert '<label for="message">' in response.text


def test_welcome_is_english_with_accept_language_en(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()

    response = client.get("/", headers={"Accept-Language": "en-GB,en;q=0.9"})

    assert "I help you prepare" in response.text
    assert 'lang="en"' in response.text


def test_chat_round_trip_renders_reply_and_citation_link(
    make_client: Callable[..., TestClient],
) -> None:
    fake = FakeClaudeClient(
        script=[text_response("Serve **appuntamento** online [fonte: ds549]\n<lang>it</lang>")]
    )
    client = make_client(fake)

    response = client.post("/chat", data={"message": "Devo rinnovare la carta"})

    assert response.status_code == 200
    assert "<strong>appuntamento</strong>" in response.text
    assert 'class="cite"' in response.text
    assert "href=" in response.text


def test_without_api_key_the_fallback_message_is_shown(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client(None)

    response = client.post("/chat", data={"message": "Ciao"})

    assert response.status_code == 200
    assert "comune.milano.it" in response.text


def test_without_api_key_the_fallback_follows_the_browser_language(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client(None)

    response = client.post(
        "/chat", data={"message": "Hello"}, headers={"Accept-Language": "en-GB,en;q=0.9"}
    )

    assert response.status_code == 200
    assert "Mi dispiace" not in response.text
    assert "comune.milano.it" in response.text


def test_personal_data_never_reaches_the_agent_unredacted(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    fake = FakeClaudeClient(script=[text_response("Va bene.\n<lang>it</lang>")])
    client = make_client(fake)

    response = client.post(
        "/chat", data={"message": f"Il mio codice fiscale è {FAKE_CF}, email {FAKE_EMAIL}"}
    )

    sent = repr([call.messages for call in fake.calls])
    assert FAKE_CF not in sent and FAKE_EMAIL not in sent
    assert FAKE_CF not in response.text and FAKE_EMAIL not in response.text
    assert FAKE_CF not in repr(fake_repo.calls) and FAKE_EMAIL not in repr(fake_repo.calls)


def _appointment_script() -> FakeClaudeClient:
    day = FUTURE_DAY.isoformat()
    return FakeClaudeClient(
        script=[
            tool_response(
                (
                    "identify_case",
                    {
                        "service_id": "carta-identita",
                        "variant": "rinnovo",
                        "answers": {"motivo": "rinnovo"},
                        "confirmed": True,
                    },
                ),
                ("record_appointment", {"date": day, "time": "10:30"}),
            ),
            text_response("Appuntamento registrato [fonte: ds549]\n<lang>it</lang>"),
        ]
    )


def test_contact_form_appears_only_after_an_appointment_event(
    make_client: Callable[..., TestClient],
) -> None:
    plain = make_client(FakeClaudeClient(script=[text_response("Ciao!\n<lang>it</lang>")]))
    with_appointment = make_client(_appointment_script())

    before = plain.post("/chat", data={"message": "Ciao"})
    after = with_appointment.post("/chat", data={"message": "Ho appuntamento"})

    assert 'id="contact"' not in before.text
    assert 'id="contact"' in after.text


def test_case_confirmed_creates_case_with_structured_fields_only(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    client = make_client(_appointment_script())

    client.post("/chat", data={"message": "Rinnovo carta, appuntamento il 15 gennaio"})

    created = [kw for name, kw in fake_repo.calls if name == "create_case"]
    assert len(created) == 1
    assert created[0]["service_id"] == "carta-identita"
    assert all(isinstance(v, str | int | dict | date | type(None)) for v in created[0].values())
    assert "update_case" in fake_repo.names()


def test_contact_consents_are_unchecked_by_default(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client(_appointment_script())

    response = client.post("/chat", data={"message": "Ho appuntamento"})

    for name in ("consent_reminder", "consent_followup", "consent_correction"):
        tag = response.text.split(f'name="{name}"')[1].split(">")[0]
        assert "checked" not in tag


def test_ics_download_after_appointment(make_client: Callable[..., TestClient]) -> None:
    client = make_client(_appointment_script())
    client.post("/chat", data={"message": "Ho appuntamento"})

    response = client.get("/case.ics")

    assert response.status_code == 200
    assert "BEGIN:VCALENDAR" in response.text
    assert "DTSTART:20300115T" in response.text


def test_health_still_works(make_client: Callable[..., TestClient]) -> None:
    client = make_client()

    response = client.get("/health")

    assert response.json() == {"status": "ok", "service": "assistant_web"}


def test_outcome_told_in_chat_is_saved_on_the_case(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    fake = FakeClaudeClient(
        script=[
            tool_response(
                ("identify_case", {"service_id": "carta-identita", "confirmed": True}),
                ("record_outcome", {"outcome": "missing", "missing_requirement_id": "inventato"}),
            ),
            text_response("<lang>it</lang>Grazie, ne terremo conto."),
        ]
    )
    client = make_client(fake)

    client.post("/chat", data={"message": "mancava un foglio"})

    [outcome] = [kw for name, kw in fake_repo.calls if name == "record_outcome"]
    assert outcome["outcome"] == "missing" and outcome["closed_in_time"] is False
    assert outcome["missing_requirement_id"] is None


def test_missing_procedure_is_recorded_as_a_structured_case(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    fake = FakeClaudeClient(
        script=[
            tool_response(("report_missing_procedure", {"summary_generalized": "permesso ZTL"})),
            text_response("<lang>it</lang>Non e' nel catalogo."),
        ]
    )
    client = make_client(fake)

    client.post("/chat", data={"message": "ztl"})

    [created] = [kw for name, kw in fake_repo.calls if name == "create_case"]
    assert created["service_id"] == "non-in-catalogo" and created["answers"] == {}
    [outcome] = [kw for name, kw in fake_repo.calls if name == "record_outcome"]
    assert outcome["cause"] == "procedura-mancante"


def test_case_created_after_appointment_carries_the_week(
    make_client: Callable[..., TestClient], fake_repo: Any
) -> None:
    fake = FakeClaudeClient(
        script=[
            tool_response(
                ("record_appointment", {"date": "2030-01-15", "time": "09:00"}),
                ("identify_case", {"service_id": "carta-identita", "confirmed": True}),
            ),
            text_response("<lang>it</lang>Fatto [fonte: ds549]"),
        ]
    )
    client = make_client(fake)

    client.post("/chat", data={"message": "ho appuntamento"})

    [created] = [kw for name, kw in fake_repo.calls if name == "create_case"]
    assert str(created["appointment_week"]) == "2030-01-14"
