"""Preparazione dei dati per i template del pannello (storie B13, C11).

Solo aggregazioni di righe gia' filtrate con la soglia k dalle viste ``analytics``:
una cella assente o nulla diventa ``None`` e il template scrive "dati insufficienti".
"""

from collections import defaultdict
from dataclasses import dataclass

from onevisit_analytics import CauseCount, Effect, ServiceTrend, WeeklyData
from onevisit_db.repo import (
    FirstVisitRateRow,
    GapsByCauseRow,
    InterventionEffectRow,
    WeeklyFirstVisitRow,
)


@dataclass(frozen=True)
class Cell:
    """Una cella di tasso: ``rate`` nullo sotto soglia."""

    cases: int
    rate: float | None


@dataclass(frozen=True)
class Matrix:
    """Tabella servizio per colonna (lingua o categoria)."""

    columns: list[str]
    rows: dict[str, dict[str, Cell | None]]


def rate_by(rows: list[FirstVisitRateRow], field: str) -> Matrix:
    """Tasso per servizio e per ``language`` o ``category`` sommando i gruppi visibili."""
    totals: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        column = str(getattr(row, field) or "non indicata")
        totals[(row.service_id, column)][0] += row.cases
        totals[(row.service_id, column)][1] += row.closed_first_visit
    columns = sorted({c for _, c in totals})
    services = sorted({s for s, _ in totals})
    matrix: dict[str, dict[str, Cell | None]] = {}
    for service in services:
        matrix[service] = {}
        for column in columns:
            cases, closed = totals.get((service, column), (0, 0))
            matrix[service][column] = Cell(cases, closed / cases) if cases else None
    return Matrix(columns=columns, rows=matrix)


def rate_by_service(rows: list[WeeklyFirstVisitRow]) -> dict[str, Cell]:
    """Tasso complessivo per servizio dalle settimane sopra soglia."""
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        totals[row.service_id][0] += row.cases
        totals[row.service_id][1] += row.closed_first_visit
    return {s: Cell(c, k / c if c else None) for s, (c, k) in sorted(totals.items())}


def weekly_series(rows: list[WeeklyFirstVisitRow]) -> dict[str, object]:
    """Dati per il grafico a linee: settimane e una serie per servizio."""
    weeks = sorted({r.week for r in rows})
    services = sorted({r.service_id for r in rows})
    by_key = {(r.service_id, r.week): r.rate for r in rows}
    return {
        "labels": [w.isoformat() for w in weeks],
        "series": [
            {"label": s, "data": [_pct(by_key.get((s, w))) for w in weeks]} for s in services
        ],
    }


def _pct(value: float | None) -> float | None:
    return None if value is None else round(float(value) * 100, 1)


def weekly_data(
    weekly: list[WeeklyFirstVisitRow],
    causes: list[GapsByCauseRow],
    effects: list[InterventionEffectRow],
    *,
    k_threshold: int,
) -> WeeklyData:
    """Ingresso della sintesi settimanale: ultime due settimane per servizio, cause, effetti."""
    trends = []
    for service in sorted({r.service_id for r in weekly}):
        series = sorted((r for r in weekly if r.service_id == service), key=lambda r: r.week)
        now = float(series[-1].rate) if series else None
        before = float(series[-2].rate) if len(series) > 1 else None
        trends.append(ServiceTrend(service_id=service, rate_now=now, rate_before=before))
    return WeeklyData(
        k_threshold=k_threshold,
        trends=trends,
        causes=[CauseCount(cause=c.cause, open_gaps=c.open_gaps, cases=c.cases) for c in causes],
        effects=[
            Effect(
                service_id=e.service_id,
                requirement_id=e.requirement_id,
                rate_before=None if e.rate_before is None else float(e.rate_before),
                rate_after=None if e.rate_after is None else float(e.rate_after),
            )
            for e in effects
        ],
    )
