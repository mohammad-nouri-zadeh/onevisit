"""Validazione del catalogo: citazioni alla lettera, fonti esistenti, date (storia A2)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from onevisit_knowledge import check_catalog, inspect_catalog, normalize, split_front_matter

REAL_DATA = Path(__file__).resolve().parents[3] / "data"


def test_valid_fixture_has_no_errors(data_dir: Path) -> None:
    assert check_catalog(data_dir) == []
    report = inspect_catalog(data_dir)
    assert report.counts["verified"] == 4
    assert report.offices == 3
    assert report.offices_with_issues == 1


def test_real_repository_data_is_valid() -> None:
    assert check_catalog(REAL_DATA) == []


def test_quote_not_in_page(make_dataset: Callable[..., Path]) -> None:
    def mutate(service: dict[str, Any]) -> None:
        service["requirements"][1]["quote"] = "Frase inventata che non esiste."

    errors = check_catalog(make_dataset(mutate))

    assert len(errors) == 1
    assert "quote not found" in errors[0]
    assert "vecchia-carta" in errors[0]


def test_quote_in_front_matter_does_not_count(make_dataset: Callable[..., Path]) -> None:
    def mutate(service: dict[str, Any]) -> None:
        service["requirements"][1]["quote"] = "https://example.org/demo"

    assert any("quote not found" in e for e in check_catalog(make_dataset(mutate)))


def test_unknown_source(make_dataset: Callable[..., Path]) -> None:
    def mutate(service: dict[str, Any]) -> None:
        service["requirements"][3]["source_id"] = "fonte-fantasma"

    errors = check_catalog(make_dataset(mutate))

    assert errors == ["servizio-demo.json requirement 'costo': unknown source_id 'fonte-fantasma'"]


def test_verified_without_date_or_quote(make_dataset: Callable[..., Path]) -> None:
    def mutate(service: dict[str, Any]) -> None:
        service["requirements"][0]["verified_at"] = None
        service["requirements"][2]["quote"] = ""
        service["steps"][1]["verified_at"] = "ieri"

    errors = check_catalog(make_dataset(mutate))

    assert any("'sempre': verified but no verified_at date" in e for e in errors)
    assert any("'genitori': verified but no quote" in e for e in errors)
    assert any("step 1: verified_at 'ieri' is not a date" in e for e in errors)


def test_when_with_unknown_question_or_option(make_dataset: Callable[..., Path]) -> None:
    def mutate(service: dict[str, Any]) -> None:
        service["requirements"][1]["when"] = {"motivo": ["furto"]}
        service["requirements"][2]["when"] = {"colore": ["rosso"]}

    errors = check_catalog(make_dataset(mutate))

    assert any("not in the options of 'motivo'" in e for e in errors)
    assert any("unknown question 'colore'" in e for e in errors)


def test_duplicate_ids_and_missing_snapshot(make_dataset: Callable[..., Path]) -> None:
    def mutate(service: dict[str, Any]) -> None:
        service["requirements"].append(dict(service["requirements"][0]))

    root = make_dataset(mutate)
    (root / "opendata" / "demo.csv").unlink()

    errors = check_catalog(root)

    assert any("duplicate id" in e for e in errors)
    assert any("snapshot opendata/demo.csv not found" in e for e in errors)


def test_todo_items_are_allowed(make_dataset: Callable[..., Path]) -> None:
    def mutate(service: dict[str, Any]) -> None:
        service["requirements"][0]["status"] = "todo"
        service["requirements"][0]["quote"] = ""

    assert check_catalog(make_dataset(mutate)) == []


def test_unknown_ente(make_dataset: Callable[..., Path]) -> None:
    def mutate(service: dict[str, Any]) -> None:
        service["steps"][0]["ente"] = "ente-fantasma"

    assert check_catalog(make_dataset(mutate)) == [
        "servizio-demo.json step 2: unknown ente 'ente-fantasma'"
    ]


def test_normalize_and_front_matter() -> None:
    assert normalize("  L\u2019Anagrafe\n  APRE ") == "l'anagrafe apre"
    meta, body = split_front_matter("---\nurl: https://example.org\n---\n\nTesto\n")
    assert meta == {"url": "https://example.org"}
    assert body == "Testo\n"
    assert split_front_matter("Nessun front matter") == ({}, "Nessun front matter")
