"""Il pannello funziona sul database vero con il ruolo app_dashboard (C12, D1)."""

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from dashboard.config import Settings
from dashboard.main import create_app
from onevisit_analytics import generate_demo_data

pytestmark = pytest.mark.db
# Password del ruolo app_dashboard in .env.example (solo sviluppo e test).
DASHBOARD_PASSWORD = "change-me-dashboard"


@pytest.fixture(scope="module")
def dashboard_client(migrated_db_url: str) -> Iterator[TestClient]:
    owner = create_engine(migrated_db_url)
    with Session(owner) as s:
        generate_demo_data(s, seed=42, weeks=8, today=date(2026, 10, 3))
        s.commit()
    url = make_url(migrated_db_url).set(username="app_dashboard", password=DASHBOARD_PASSWORD)
    engine = create_engine(url)
    app = create_app(
        Settings(session_secret="test"),
        session_factory=sessionmaker(engine, expire_on_commit=False),
    )
    client = TestClient(app)
    client.post("/login", data={"role": "redazione"})
    yield client
    engine.dispose()
    with owner.begin() as conn:
        conn.execute(text("DELETE FROM core.interventions"))
        conn.execute(text("DELETE FROM core.gaps WHERE synthetic"))
        conn.execute(text("DELETE FROM core.cases WHERE synthetic"))
    owner.dispose()


def test_pages_render_from_analytics_views(dashboard_client: TestClient) -> None:
    for path in ("/", "/gaps", "/office", "/interventions", "/summary"):
        assert dashboard_client.get(path).status_code == 200, path


def test_interventions_page_shows_before_and_after(dashboard_client: TestClient) -> None:
    text_ = dashboard_client.get("/interventions").text

    assert "documenti-esteri" in text_
    assert "71%" in text_ and "93%" in text_


def test_redazione_approves_a_gap_on_the_real_database(dashboard_client: TestClient) -> None:
    page = dashboard_client.get("/gaps?status=nuova").text
    gap_id = page.split('href="/gaps/')[1].split('"')[0]

    response = dashboard_client.post(
        f"/gaps/{gap_id}/approve",
        data={"text_it": "testo", "text_easy_it": "facile", "text_en": "text"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "corretta" in dashboard_client.get(f"/gaps/{gap_id}").text
