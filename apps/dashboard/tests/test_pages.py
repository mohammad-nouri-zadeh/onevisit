"""Le pagine del pannello si vedono con dati finti; ruoli e soglia k rispettati (C12, B10-B13)."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.config import Settings
from dashboard.main import create_app
from dashboard.testing import FakePanelData

SRC = Path(__file__).resolve().parents[1] / "src"


def test_pages_require_demo_login() -> None:
    client = TestClient(create_app(Settings(session_secret="s")))

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_says_access_is_demo() -> None:
    client = TestClient(create_app(Settings(session_secret="s")))

    response = client.get("/login")

    assert "accesso dimostrativo" in response.text.lower()
    assert "OIDC" in response.text


def test_every_page_renders_for_direzione(client_as: Callable[[str], TestClient]) -> None:
    client = client_as("direzione")

    for path in ("/", "/gaps", "/office", "/interventions", "/summary", "/context", "/settings"):
        assert client.get(path).status_code == 200, path


def test_cells_under_k_show_insufficient_data(client_as: Callable[[str], TestClient]) -> None:
    client = client_as("redazione")

    overview = client.get("/").text
    interventions = client.get("/interventions").text

    assert "dati insufficienti" in overview
    assert "dati insufficienti" in interventions


def test_overview_shows_estimate_formula_and_slot_cost(
    client_as: Callable[[str], TestClient],
) -> None:
    text = client_as("direzione").get("/").text

    assert "stima" in text.lower()
    assert "20.00 €" in text
    assert "costo per slot" in text


def test_below_threshold_gaps_are_listed_without_link(
    client_as: Callable[[str], TestClient], fake_data: FakePanelData
) -> None:
    below = fake_data.gaps[2]

    text = client_as("redazione").get("/gaps").text

    assert "Gruppi sotto soglia" in text
    assert f"/gaps/{below.id}" not in text
    assert "fonte non comunale" in text
    assert "Polizia di Stato" in text


def test_approve_button_visible_only_to_redazione(
    client_as: Callable[[str], TestClient], fake_data: FakePanelData
) -> None:
    gap_id = fake_data.gaps[0].id

    as_editor = client_as("redazione").get(f"/gaps/{gap_id}").text
    as_office = client_as("ufficio").get(f"/gaps/{gap_id}").text

    assert "Approva la correzione" in as_editor
    assert "Approva la correzione" not in as_office


def test_approve_is_forbidden_for_other_roles(
    client_as: Callable[[str], TestClient], fake_data: FakePanelData
) -> None:
    gap_id = fake_data.gaps[0].id

    for role in ("ufficio", "direzione"):
        response = client_as(role).post(f"/gaps/{gap_id}/approve", data={"text_it": "x"})
        assert response.status_code == 403
    assert fake_data.approved == []


def test_redazione_approves_and_access_is_logged(
    client_as: Callable[[str], TestClient], fake_data: FakePanelData
) -> None:
    gap_id = fake_data.gaps[0].id
    client = client_as("redazione")

    client.get(f"/gaps/{gap_id}")
    response = client.post(
        f"/gaps/{gap_id}/approve",
        data={"text_it": "a", "text_easy_it": "b", "text_en": "c"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert fake_data.approved == [gap_id]
    assert ("redazione", "view_gap", str(gap_id)) in fake_data.access


def test_settings_forbidden_for_non_direzione(client_as: Callable[[str], TestClient]) -> None:
    assert client_as("redazione").get("/settings").status_code == 403


def test_direzione_saves_settings(
    client_as: Callable[[str], TestClient], fake_data: FakePanelData
) -> None:
    response = client_as("direzione").post(
        "/settings",
        data={"k_threshold": "6", "cost_per_slot_eur": "25", "window_weeks": "4"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert fake_data.cfg["cost_per_slot_eur"] == 25


def test_summary_without_api_key_uses_rule_text(client_as: Callable[[str], TestClient]) -> None:
    text = client_as("direzione").get("/summary").text

    assert "Testo generato da regola" in text
    assert "Interventi consigliati" in text


def test_context_cites_open_datasets(client_as: Callable[[str], TestClient]) -> None:
    text = client_as("ufficio").get("/context").text

    for dataset in ("ds1959", "ds1702", "ds1511", "ds1512", "ds74"):
        assert dataset in text


def test_dashboard_sources_never_mention_pii_schema() -> None:
    offenders = [
        str(path)
        for path in SRC.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".html", ".js", ".sql", ".css"}
        and "pii." in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_k_threshold_below_five_is_rejected(client_as: Callable[[str], TestClient]) -> None:
    response = client_as("direzione").post(
        "/settings",
        data={"k_threshold": "1", "cost_per_slot_eur": "25", "window_weeks": "4"},
        follow_redirects=False,
    )

    assert response.status_code == 422


def test_gap_detail_below_k_hides_count_summary_and_examples(
    client_as: Callable[[str], TestClient], fake_data: FakePanelData
) -> None:
    below = fake_data.gaps[2]
    assert below.summary or below.examples

    text = client_as("redazione").get(f"/gaps/{below.id}").text

    assert "dati insufficienti" in text
    if below.summary:
        assert below.summary not in text
    for example in below.examples:
        assert str(example) not in text


def test_approve_form_asks_for_citizen_requirement_not_page_draft(
    client_as: Callable[[str], TestClient], fake_data: FakePanelData
) -> None:
    gap = fake_data.gaps[0]

    text = client_as("redazione").get(f"/gaps/{gap.id}").text

    assert "Requisito per il cittadino" in text
    assert '<textarea id="text_it" name="text_it" required></textarea>' in text


def test_base_template_uses_local_design_system_only() -> None:
    base = (SRC / "dashboard" / "templates" / "base.html").read_text(encoding="utf-8")

    assert "/ui/fonts.css" in base
    assert "/ui/onevisit.css" in base
    assert "/ui/vendor/htmx.min.js" in base
    assert "/ui/vendor/chart.umd.min.js" in base
    for third_party in ("unpkg.com", "cdn.jsdelivr.net", "fonts.googleapis"):
        assert third_party not in base


def test_design_system_assets_are_served() -> None:
    client = TestClient(create_app(Settings(session_secret="s")))

    for path in (
        "/ui/onevisit.css",
        "/ui/fonts.css",
        "/ui/vendor/chart.umd.min.js",
        "/ui/vendor/htmx.min.js",
    ):
        assert client.get(path).status_code == 200, path


def test_rendered_pages_call_no_third_party_hosts(client_as: Callable[[str], TestClient]) -> None:
    client = client_as("direzione")

    for path in ("/", "/gaps", "/office", "/interventions", "/summary", "/context", "/settings"):
        text = client.get(path).text
        for third_party in ("unpkg.com", "cdn.jsdelivr.net", "fonts.googleapis"):
            assert third_party not in text, (path, third_party)


def test_current_section_is_marked_in_navigation(client_as: Callable[[str], TestClient]) -> None:
    text = client_as("redazione").get("/gaps").text

    assert '<a href="/gaps" aria-current="page">Lacune</a>' in text
    assert '<a href="/" aria-current="page">' not in text
