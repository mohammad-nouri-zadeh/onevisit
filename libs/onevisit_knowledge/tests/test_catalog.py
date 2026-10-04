"""Regole della checklist, sedi, enti e scadenza delle fonti (storie A2, C4)."""

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import pytest

from onevisit_knowledge import (
    APPROVED_CORRECTION_SOURCE_ID,
    ApprovedCorrection,
    CatalogError,
    KnowledgeError,
    haversine_km,
    load_catalog,
)

REAL_DATA = Path(__file__).resolve().parents[3] / "data"


def test_services_summary_counts_verified(data_dir: Path) -> None:
    [summary] = load_catalog(data_dir).services()

    assert summary.id == "servizio-demo"
    assert summary.title_en == "Demo service"
    assert (summary.verified_requirements, summary.total_requirements) == (3, 4)


def test_service_keeps_only_verified_steps_sorted(data_dir: Path) -> None:
    service = load_catalog(data_dir).service("servizio-demo")

    assert service is not None
    assert [s.order for s in service.steps] == [1]
    assert [q.id for q in service.deciding_questions] == ["motivo", "eta", "scadenza"]
    assert load_catalog(data_dir).service("non-esiste") is None


def test_service_with_drafts_shows_all_steps(data_dir: Path) -> None:
    service = load_catalog(data_dir, include_drafts=True).service("servizio-demo")

    assert service is not None
    assert [s.order for s in service.steps] == [1, 2]


def test_checklist_without_answers_lists_questions_still_to_ask(data_dir: Path) -> None:
    checklist = load_catalog(data_dir).checklist("servizio-demo", {})

    assert [i.id for i in checklist.items] == ["sempre"]
    assert checklist.items[0].lead_time_days == 7
    assert checklist.items[0].origin == "source"
    assert checklist.still_to_ask == ["eta", "motivo"]
    assert checklist.not_yet_verified == ["costo"]
    assert [s.id for s in checklist.sources] == ["dataset-demo"]


def test_checklist_applies_when_conditions(data_dir: Path) -> None:
    catalog = load_catalog(data_dir)

    renewal = catalog.checklist("servizio-demo", {"motivo": "rinnovo", "eta": "adulto"})
    first = catalog.checklist("servizio-demo", {"motivo": "prima", "eta": "minore"})

    assert [i.id for i in renewal.items] == ["sempre", "vecchia-carta"]
    assert renewal.still_to_ask == []
    assert [i.id for i in first.items] == ["sempre", "genitori"]
    assert {s.id for s in renewal.sources} == {"dataset-demo", "pagina-demo"}


def test_checklist_drafts_include_todo_requirements(data_dir: Path) -> None:
    checklist = load_catalog(data_dir, include_drafts=True).checklist("servizio-demo", {})

    assert "costo" in [i.id for i in checklist.items]
    assert checklist.not_yet_verified == []


def test_checklist_unknown_service_raises(data_dir: Path) -> None:
    with pytest.raises(CatalogError):
        load_catalog(data_dir).checklist("non-esiste", {})
    assert issubclass(CatalogError, KnowledgeError)


def test_overlay_replaces_requirement_and_adds_new_one(data_dir: Path) -> None:
    overlays = [
        ApprovedCorrection(
            id="corr-1",
            service_id="servizio-demo",
            requirement_id="costo",
            text_it="Il costo si paga allo sportello.",
            text_en="You pay the fee at the desk.",
            approved_at=datetime(2026, 10, 2, 10, 0),
        ),
        ApprovedCorrection(
            id="corr-2",
            service_id="servizio-demo",
            text_it="Porta una fototessera recente.",
            approved_at=date(2026, 10, 3),
            when={"eta": ["minore"]},
        ),
        ApprovedCorrection(
            id="corr-3", service_id="altro", text_it="Non c'entra.", approved_at=date(2026, 10, 3)
        ),
    ]
    catalog = load_catalog(data_dir, overlays=overlays)

    adult = catalog.checklist("servizio-demo", {"motivo": "prima", "eta": "adulto"})
    minor = catalog.checklist("servizio-demo", {"motivo": "prima", "eta": "minore"})

    corrected = [i for i in adult.items if i.origin == "approved_correction"]
    assert [(i.id, i.source_id) for i in corrected] == [("costo", APPROVED_CORRECTION_SOURCE_ID)]
    assert corrected[0].verified_at == date(2026, 10, 2)
    assert adult.not_yet_verified == []
    assert "corr-2" in [i.id for i in minor.items]
    assert APPROVED_CORRECTION_SOURCE_ID in {s.id for s in adult.sources}
    assert APPROVED_CORRECTION_SOURCE_ID in catalog.source_ids()


def test_source_ids_without_overlays(data_dir: Path) -> None:
    ids = load_catalog(data_dir).source_ids()

    assert ids == frozenset({"pagina-demo", "dataset-demo", "senza-data"})
    source = load_catalog(data_dir).source("dataset-demo")
    assert source is not None
    assert source.retrieved_at == date(2026, 10, 1)
    assert source.notes == "nota, con virgola"


def test_is_stale_by_retrieved_at(data_dir: Path) -> None:
    catalog = load_catalog(
        data_dir,
        overlays=[
            ApprovedCorrection(
                id="c", service_id="servizio-demo", text_it="x", approved_at=date(2020, 1, 1)
            )
        ],
    )
    today = date(2026, 10, 3)

    assert catalog.is_stale("pagina-demo", today=today, max_days=30) is True
    assert catalog.is_stale("pagina-demo", today=today, max_days=40) is False
    assert catalog.is_stale("dataset-demo", today=today, max_days=30) is False
    assert catalog.is_stale("senza-data", today=today, max_days=30) is True
    assert catalog.is_stale("sconosciuta", today=today, max_days=30) is True
    assert catalog.is_stale(APPROVED_CORRECTION_SOURCE_ID, today=today, max_days=30) is False


def test_offices_filters(data_dir: Path) -> None:
    catalog = load_catalog(data_dir)

    assert [o.id for o in catalog.offices(municipio=2, limit=10)] == ["ds549-02", "ds549-03"]
    assert [o.id for o in catalog.offices(area="loreto")] == ["ds549-03"]
    assert [o.id for o in catalog.offices(area="via finta")] == ["ds549-01"]
    assert len(catalog.offices(limit=2)) == 2
    assert catalog.offices(area="nessuno") == []


def test_offices_sorted_by_distance(data_dir: Path) -> None:
    catalog = load_catalog(data_dir)

    nearest = catalog.offices(lat=45.4865, lon=9.2165, limit=3)

    assert [o.id for o in nearest] == ["ds549-03", "ds549-02", "ds549-01"]
    assert nearest[0].distance_km is not None and nearest[0].distance_km < 0.1
    assert nearest[0].nil_name == "LORETO"
    assert catalog.office("ds549-02") is not None
    office = catalog.office("ds549-02")
    assert office is not None and office.data_issues == ["Orari non aggiornati"]
    assert office.distance_km is None
    assert catalog.office("ds549-99") is None


def test_haversine_known_distance() -> None:
    # Duomo di Milano -> Stazione Centrale: circa 2,6 km in linea d'aria.
    assert haversine_km(45.4642, 9.1900, 45.4859, 9.2035) == pytest.approx(2.65, abs=0.1)
    assert haversine_km(45.0, 9.0, 45.0, 9.0) == 0.0


def test_enti_and_context(data_dir: Path) -> None:
    catalog = load_catalog(data_dir)

    assert [e.id for e in catalog.enti()] == ["comune-prova"]
    assert catalog.context_tables() == {"arrivi": [{"anno": "2024", "arrivi": "100"}]}


def test_invalid_json_raises_catalog_error(make_dataset: Callable[..., Path]) -> None:
    root = make_dataset()
    (root / "services" / "rotto.json").write_text("{", encoding="utf-8")

    with pytest.raises(CatalogError):
        load_catalog(root)


def test_real_data_loads_and_hides_todo() -> None:
    catalog = load_catalog(REAL_DATA)

    ids = {s.id for s in catalog.services()}
    assert {"carta-identita", "iscrizione-anagrafica-extra-ue"} <= ids
    answers = {"motivo": "rinnovo", "eta": "adulto", "cittadinanza": "extra-ue"}
    checklist = catalog.checklist("carta-identita", answers)
    assert all(i.source_id in catalog.source_ids() for i in checklist.items)
    item_ids = {i.id for i in checklist.items}
    # Verificato con citazione dalla pagina del Comune: compare nella checklist.
    assert "documento-precedente" in item_ids
    # Ancora "todo" (le fonti non lo dicono): nascosto, elencato tra i non verificati.
    assert "espatrio-adulti-non-italiani" in checklist.not_yet_verified
    assert "espatrio-adulti-non-italiani" not in item_ids
    assert catalog.office("ds549-01") is not None


def test_overlay_without_when_inherits_condition_of_replaced_requirement(data_dir: Path) -> None:
    overlay = ApprovedCorrection(
        id="corr-genitori",
        service_id="servizio-demo",
        requirement_id="genitori",
        text_it="Vengono entrambi i genitori con un documento.",
        approved_at=date(2026, 10, 3),
    )
    catalog = load_catalog(data_dir, overlays=[overlay])

    adult = catalog.checklist("servizio-demo", {"motivo": "prima", "eta": "adulto"})
    minor = catalog.checklist("servizio-demo", {"motivo": "prima", "eta": "minore"})

    assert "genitori" not in [i.id for i in adult.items]
    assert "genitori" in [i.id for i in minor.items]
