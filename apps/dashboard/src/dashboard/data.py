"""Accesso ai dati del pannello (storie C12, B10-B13).

Il pannello legge solo le viste ``analytics``, ``core.gaps``, ``core.interventions`` e
``analytics.config``; scrive ``core.gaps``, ``core.interventions``, ``core.access_log``.
Mai ``pii`` ne' ``core.cases``. :class:`PanelData` permette ai test di usare dati finti.
"""

import uuid
from collections.abc import Callable
from typing import Protocol

from sqlalchemy.orm import Session

from onevisit_db import repo
from onevisit_db.repo import (
    AvoidedVisitsRow,
    FirstVisitRateRow,
    GapRow,
    GapsByCauseRow,
    GapStatus,
    InterventionEffectRow,
    WeeklyFirstVisitRow,
)


class PanelData(Protocol):
    """Operazioni del pannello sul database."""

    def first_visit_rate(self) -> list[FirstVisitRateRow]: ...
    def weekly_first_visit(self) -> list[WeeklyFirstVisitRow]: ...
    def gaps_by_cause(self) -> list[GapsByCauseRow]: ...
    def intervention_effect(self) -> list[InterventionEffectRow]: ...
    def avoided_visits(self) -> list[AvoidedVisitsRow]: ...
    def config(self) -> dict[str, float]: ...
    def list_gaps(
        self, *, cause: str | None, service_id: str | None, status: GapStatus | None
    ) -> list[GapRow]: ...
    def get_gap(self, gap_id: uuid.UUID) -> GapRow | None: ...
    def approve_gap(
        self, gap_id: uuid.UUID, *, role: str, text_it: str, text_easy_it: str, text_en: str
    ) -> uuid.UUID: ...
    def archive_gap(self, gap_id: uuid.UUID, *, role: str, reason: str) -> None: ...
    def set_config(self, key: str, value: float, *, role: str) -> None: ...
    def log_access(self, *, role: str, action: str, object_id: str | None) -> None: ...


class SqlPanelData:
    """Implementazione su Postgres con il ruolo ``app_dashboard``."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._sessions = session_factory

    def first_visit_rate(self) -> list[FirstVisitRateRow]:
        with self._sessions() as s:
            return repo.read_first_visit_rate(s)

    def weekly_first_visit(self) -> list[WeeklyFirstVisitRow]:
        with self._sessions() as s:
            return repo.read_weekly_first_visit(s)

    def gaps_by_cause(self) -> list[GapsByCauseRow]:
        with self._sessions() as s:
            return repo.read_gaps_by_cause(s)

    def intervention_effect(self) -> list[InterventionEffectRow]:
        with self._sessions() as s:
            return repo.read_intervention_effect(s)

    def avoided_visits(self) -> list[AvoidedVisitsRow]:
        with self._sessions() as s:
            return repo.read_avoided_visits(s)

    def config(self) -> dict[str, float]:
        with self._sessions() as s:
            return repo.read_config(s)

    def list_gaps(
        self, *, cause: str | None, service_id: str | None, status: GapStatus | None
    ) -> list[GapRow]:
        with self._sessions() as s:
            return repo.list_gaps(s, cause=cause, service_id=service_id, status=status)

    def get_gap(self, gap_id: uuid.UUID) -> GapRow | None:
        with self._sessions() as s:
            return repo.get_gap(s, gap_id)

    def approve_gap(
        self, gap_id: uuid.UUID, *, role: str, text_it: str, text_easy_it: str, text_en: str
    ) -> uuid.UUID:
        with self._sessions() as s:
            intervention_id = repo.approve_gap(
                s,
                gap_id,
                approved_by=role,
                text_it=text_it,
                text_easy_it=text_easy_it,
                text_en=text_en,
            )
            repo.log_access(s, role=role, action="approve_gap", object_id=str(gap_id))
            s.commit()
            return intervention_id

    def archive_gap(self, gap_id: uuid.UUID, *, role: str, reason: str) -> None:
        with self._sessions() as s:
            repo.archive_gap(s, gap_id, reason=reason)
            repo.log_access(s, role=role, action="archive_gap", object_id=str(gap_id))
            s.commit()

    def set_config(self, key: str, value: float, *, role: str) -> None:
        with self._sessions() as s:
            repo.set_config(s, key, value)
            repo.log_access(s, role=role, action="set_config", object_id=key)
            s.commit()

    def log_access(self, *, role: str, action: str, object_id: str | None) -> None:
        with self._sessions() as s:
            repo.log_access(s, role=role, action=action, object_id=object_id)
            s.commit()
