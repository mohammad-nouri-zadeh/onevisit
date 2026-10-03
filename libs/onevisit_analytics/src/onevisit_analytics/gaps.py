"""Raggruppamento degli esiti negativi in lacune (storia C10).

Chiave di una lacuna: servizio, pagina (``source_id``), causa e requisito. Per ogni
esito si decide se unirlo a una lacuna aperta con la stessa chiave o crearne una
nuova; la decisione resta registrata in :class:`GapDecision`. Il raggruppamento e'
per procedura e per sede, mai per persona. Le fonti non comunali vanno all'ente
nazionale che le possiede.
"""

import uuid
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from onevisit_analytics.causes import RECIPIENT_BY_CAUSE, Cause
from onevisit_analytics.names import ensure_no_proper_names

GapKey = tuple[str, str | None, str, str | None]


class NegativeOutcome(BaseModel):
    """Un esito negativo gia' classificato (solo campi strutturati)."""

    model_config = ConfigDict(frozen=True)

    case_id: uuid.UUID
    service_id: str
    source_id: str | None
    cause: Cause
    requirement_id: str | None
    office_id: str | None
    week: date


class OpenGap(BaseModel):
    """Lacuna aperta gia' salvata, con cui confrontare i nuovi esiti."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    service_id: str
    source_id: str | None
    cause: Cause
    requirement_id: str | None


class GapDecision(BaseModel):
    """Decisione registrata per un esito: unirlo a una lacuna o crearne una nuova."""

    model_config = ConfigDict(frozen=True)

    case_id: uuid.UUID
    action: Literal["join-existing", "new"]
    gap_id: uuid.UUID


class GapProposal(BaseModel):
    """Lacuna proposta (nuova o aggiornata) con i casi collegati."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    is_new: bool
    service_id: str
    source_id: str | None
    cause: Cause
    requirement_id: str | None
    recipient: str
    owner_ente: str | None
    title: str
    summary: str
    examples: list[str]
    case_ids: list[uuid.UUID]
    offices: list[str]
    first_week: date
    last_week: date

    @property
    def national(self) -> bool:
        """Vero se la pagina e' di un ente non comunale ("fonte non comunale")."""
        return self.recipient == "ente-nazionale"


class GapGrouping(BaseModel):
    """Risultato del raggruppamento: lacune e decisioni."""

    model_config = ConfigDict(frozen=True)

    gaps: list[GapProposal]
    decisions: list[GapDecision]


def _key(service_id: str, source_id: str | None, cause: Cause, req: str | None) -> GapKey:
    return (service_id, source_id, cause.value, req)


def group_into_gaps(
    outcomes: Sequence[NegativeOutcome],
    *,
    open_gaps: Sequence[OpenGap] = (),
    national_owners: Mapping[str, str] | None = None,
) -> GapGrouping:
    """Raggruppa gli esiti per servizio e pagina; unisce alle lacune aperte se possibile.

    ``national_owners`` associa i ``source_id`` non comunali al nome dell'ente titolare.
    """
    owners = national_owners or {}
    existing = {_key(g.service_id, g.source_id, g.cause, g.requirement_id): g for g in open_gaps}
    buckets: dict[GapKey, list[NegativeOutcome]] = {}
    for item in sorted(outcomes, key=lambda o: (o.week, str(o.case_id))):
        key = _key(item.service_id, item.source_id, item.cause, item.requirement_id)
        buckets.setdefault(key, []).append(item)
    gaps: list[GapProposal] = []
    decisions: list[GapDecision] = []
    for key, items in buckets.items():
        found = existing.get(key)
        gap_id = found.id if found is not None else uuid.uuid4()
        action: Literal["join-existing", "new"] = "join-existing" if found else "new"
        decisions.extend(
            GapDecision(case_id=i.case_id, action=action, gap_id=gap_id) for i in items
        )
        gaps.append(_proposal(gap_id, found is None, items, owners))
    return GapGrouping(gaps=gaps, decisions=decisions)


def _proposal(
    gap_id: uuid.UUID, is_new: bool, items: list[NegativeOutcome], owners: Mapping[str, str]
) -> GapProposal:
    first = items[0]
    owner = owners.get(first.source_id) if first.source_id else None
    recipient = "ente-nazionale" if owner else RECIPIENT_BY_CAUSE[first.cause]
    title = f"{first.cause.value}: {first.requirement_id or 'requisito non indicato'}"
    # Nessun conteggio nel testo salvato: il numero di casi sta solo in case_count, che il
    # pannello nasconde sotto la soglia k (C11).
    summary = (
        f"Esiti negativi per {first.service_id}, causa {first.cause.value}, "
        f"pagina {first.source_id or 'non indicata'}."
    )
    examples = sorted({_example(i) for i in items})
    ensure_no_proper_names([title, summary, *examples])
    return GapProposal(
        id=gap_id,
        is_new=is_new,
        service_id=first.service_id,
        source_id=first.source_id,
        cause=first.cause,
        requirement_id=first.requirement_id,
        recipient=recipient,
        owner_ente=owner,
        title=title,
        summary=summary,
        examples=examples,
        case_ids=[i.case_id for i in items],
        offices=sorted({i.office_id for i in items if i.office_id}),
        first_week=min(i.week for i in items),
        last_week=max(i.week for i in items),
    )


def _example(item: NegativeOutcome) -> str:
    """Esempio generalizzato: mai il testo del cittadino, solo procedura e requisito."""
    return (
        f"pratica {item.service_id}: mancava {item.requirement_id or 'un requisito non previsto'}"
    )
