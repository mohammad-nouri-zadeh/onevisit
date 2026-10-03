"""Dati finti in memoria per i test del pannello e delle app che lo usano (nessun database)."""

import uuid
from datetime import UTC, date, datetime

from onevisit_db.repo import (
    AvoidedVisitsRow,
    FirstVisitRateRow,
    GapRow,
    GapsByCauseRow,
    GapStatus,
    InterventionEffectRow,
    WeeklyFirstVisitRow,
)

NOW = datetime(2026, 9, 28, 10, tzinfo=UTC)


def make_gap(**fields: object) -> GapRow:
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "service_id": "iscrizione-anagrafica-extra-ue",
        "cause": "procedura-mancante",
        "source_id": "residenza-estero",
        "title": "Documenti esteri: traduzione non descritta",
        "summary": "6 esiti negativi",
        "examples": ["pratica iscrizione: mancava documenti-esteri"],
        "status": "nuova",
        "recipient": "redazione",
        "owner_ente": None,
        "requirement_id": "documenti-esteri",
        "draft_it": "Bozza italiana",
        "draft_easy_it": "Bozza facile",
        "draft_en": "English draft",
        "case_count": 6,
        "first_seen": NOW,
        "last_seen": NOW,
        "archived_reason": None,
        "synthetic": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(fields)
    return GapRow.model_validate(base)


class FakePanelData:
    """Implementazione in memoria di PanelData che registra le scritture."""

    def __init__(self) -> None:
        self.gaps = [
            make_gap(),
            make_gap(
                cause="ente-o-ufficio-sbagliato",
                source_id="permesso-soggiorno",
                recipient="ente-nazionale",
                owner_ente="Polizia di Stato",
                case_count=5,
                title="Permesso: ufficio non chiaro",
            ),
            make_gap(cause="richiesta-non-prevista", case_count=2, title="Sotto soglia"),
        ]
        self.cfg = {"k_threshold": 5.0, "cost_per_slot_eur": 20.0, "window_weeks": 4.0}
        self.access: list[tuple[str, str, str | None]] = []
        self.approved: list[uuid.UUID] = []

    def first_visit_rate(self) -> list[FirstVisitRateRow]:
        return [
            FirstVisitRateRow(
                service_id="carta-identita",
                category="italiana",
                language="it",
                cases=40,
                closed_first_visit=36,
                rate=0.9,
            ),
            FirstVisitRateRow(
                service_id="iscrizione-anagrafica-extra-ue",
                category="extra-ue",
                language="ar",
                cases=20,
                closed_first_visit=15,
                rate=0.75,
            ),
        ]

    def weekly_first_visit(self) -> list[WeeklyFirstVisitRow]:
        return [
            WeeklyFirstVisitRow(
                service_id="carta-identita",
                week=date(2026, 9, 14),
                cases=30,
                closed_first_visit=27,
                rate=0.9,
            ),
            WeeklyFirstVisitRow(
                service_id="carta-identita",
                week=date(2026, 9, 21),
                cases=30,
                closed_first_visit=24,
                rate=0.8,
            ),
        ]

    def gaps_by_cause(self) -> list[GapsByCauseRow]:
        return [
            GapsByCauseRow(cause="procedura-mancante", gaps=1, open_gaps=1, cases=6),
            GapsByCauseRow(cause="richiesta-non-prevista", gaps=1, open_gaps=1, cases=None),
        ]

    def intervention_effect(self) -> list[InterventionEffectRow]:
        return [
            InterventionEffectRow(
                intervention_id=uuid.uuid4(),
                gap_id=None,
                service_id="carta-identita",
                requirement_id="fototessera",
                approved_at=NOW,
                window_weeks=4,
                cases_before=3,
                rate_before=None,
                cases_after=None,
                rate_after=None,
            )
        ]

    def avoided_visits(self) -> list[AvoidedVisitsRow]:
        return [
            AvoidedVisitsRow(
                service_id="carta-identita",
                interventions=1,
                avoided_visits=None,
                cost_per_slot_eur=20.0,
                avoided_cost_eur=None,
            )
        ]

    def config(self) -> dict[str, float]:
        return dict(self.cfg)

    def list_gaps(
        self, *, cause: str | None, service_id: str | None, status: GapStatus | None
    ) -> list[GapRow]:
        rows = [
            g
            for g in self.gaps
            if (cause is None or g.cause == cause)
            and (service_id is None or g.service_id == service_id)
            and (status is None or g.status == status)
        ]
        return sorted(rows, key=lambda g: -g.case_count)

    def get_gap(self, gap_id: uuid.UUID) -> GapRow | None:
        return next((g for g in self.gaps if g.id == gap_id), None)

    def approve_gap(
        self, gap_id: uuid.UUID, *, role: str, text_it: str, text_easy_it: str, text_en: str
    ) -> uuid.UUID:
        self.approved.append(gap_id)
        self.access.append((role, "approve_gap", str(gap_id)))
        return uuid.uuid4()

    def archive_gap(self, gap_id: uuid.UUID, *, role: str, reason: str) -> None:
        self.access.append((role, "archive_gap", str(gap_id)))

    def set_config(self, key: str, value: float, *, role: str) -> None:
        self.cfg[key] = value

    def log_access(self, *, role: str, action: str, object_id: str | None) -> None:
        self.access.append((role, action, object_id))
