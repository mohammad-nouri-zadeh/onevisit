"""Con il database vero: il testo del cittadino con dati personali non finisce in tabella (C9)."""

from collections.abc import Callable
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from assistant_web.config import Settings
from assistant_web.main import create_app
from onevisit_agent.testing import FakeClaudeClient, text_response, tool_response

FAKE_CF = "RSSMRA80A01F205X"
FAKE_EMAIL = "mario.test@example.org"


@pytest.mark.db
def test_personal_data_in_chat_never_reaches_the_database(
    migrated_db_url: str, settings_factory: Callable[..., Settings]
) -> None:
    fake = FakeClaudeClient(
        script=[
            tool_response(
                ("identify_case", {"service_id": "carta-identita", "confirmed": True}),
                ("record_appointment", {"date": date(2030, 1, 15).isoformat(), "time": "09:00"}),
            ),
            text_response("Fatto [fonte: ds549]\n<lang>it</lang>"),
        ]
    )
    app = create_app(settings_factory(database_url=migrated_db_url), claude_client=fake)
    client = TestClient(app, raise_server_exceptions=False)

    client.post("/chat", data={"message": f"CF {FAKE_CF}, scrivimi a {FAKE_EMAIL}"})
    client.post("/contact", data={"choice": "email", "email": FAKE_EMAIL})

    engine = create_engine(migrated_db_url)
    with engine.connect() as conn:
        dump = repr(conn.execute(text("SELECT * FROM core.cases")).all())
        dump += repr(conn.execute(text("SELECT * FROM core.case_answers")).all())
        dump += repr(conn.execute(text("SELECT * FROM pii.contacts")).all())
        cases = conn.execute(text("SELECT count(*) FROM core.cases")).scalar_one()
    engine.dispose()
    assert cases == 1
    assert FAKE_CF not in dump and FAKE_EMAIL not in dump
