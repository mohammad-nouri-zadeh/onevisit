"""Dati sintetici dello scenario demo (storia D1).

Circa 400 casi in 8 settimane per i due servizi, tutti con ``synthetic=True``. La storia:
dalla settimana 2 emerge una lacuna "procedura-mancante" per l'iscrizione extra-UE
(traduzione e legalizzazione dei documenti esteri, requisito ``documenti-esteri``);
nella settimana 4 supera la soglia (5 casi in 4 settimane); nella settimana 5 la
redazione approva la correzione; dopo, il tasso di chiusura al primo appuntamento sale.
Generatore deterministico (``random.Random(seed)``) e idempotente: cancella prima le
righe sintetiche precedenti. Nessun dato personale: solo campi strutturati.
"""

import random
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from onevisit_analytics.demo_script import (
    CIE,
    ISCRIZIONE,
    MAIN_GAP_KEY,
    NATIONAL_OWNERS,
    SCRIPTED_GAPS,
    DemoSummary,
    ScriptedGap,
    case_profile,
    other_failure_rate,
    threshold_week,
)
from onevisit_analytics.drafts import GapForDraft, draft_correction
from onevisit_analytics.gaps import GapProposal, NegativeOutcome, group_into_gaps
from onevisit_db.models import Case, CaseAnswer, Gap, GapCase, Intervention

ROME = ZoneInfo("Europe/Rome")
# Settimana (1-based) in cui la redazione approva la correzione della lacuna principale.
INTERVENTION_WEEK = 5
# Ruolo dimostrativo che approva: mai un nome.
DEMO_APPROVER = "redazione-demo"
# Casi per settimana e servizio: 30 + 20 = 50 a settimana, circa 400 in 8 settimane.
CASES_PER_WEEK = {CIE: 30, ISCRIZIONE: 20}
# Quota di casi senza esito registrato (il cittadino non ha risposto al follow-up).
NO_REPLY_RATE = 0.04
# Soglia k usata per decidere quali lacune ricevono la bozza.
K_THRESHOLD = 5
# Ora locale dell'approvazione dimostrativa.
APPROVAL_HOUR = 9


def _week_start(today: date, weeks: int, week: int) -> date:
    monday = today - timedelta(days=today.weekday())
    return monday - timedelta(weeks=weeks) + timedelta(weeks=week - 1)


def _uuid(rng: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def _at(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=ROME).astimezone(UTC)


def wipe_synthetic(session: Session) -> None:
    """Cancella casi, lacune e interventi sintetici delle esecuzioni precedenti."""
    synthetic_gaps = select(Gap.id).where(Gap.synthetic.is_(True)).scalar_subquery()
    session.execute(delete(Intervention).where(Intervention.gap_id.in_(synthetic_gaps)))
    session.execute(delete(GapCase).where(GapCase.gap_id.in_(synthetic_gaps)))
    session.execute(delete(Gap).where(Gap.synthetic.is_(True)))
    session.execute(delete(Case).where(Case.synthetic.is_(True)))


def generate_demo_data(
    session: Session, *, seed: int = 42, weeks: int = 8, today: date
) -> DemoSummary:
    """Genera lo scenario demo nella sessione data (il chiamante fa il commit)."""
    rng = random.Random(seed)  # noqa: S311 - dati sintetici, non crittografia
    wipe_synthetic(session)
    cases: list[dict[str, Any]] = []
    answers: list[dict[str, Any]] = []
    negatives: list[NegativeOutcome] = []
    for week in range(1, weeks + 1):
        start = _week_start(today, weeks, week)
        for service, count in CASES_PER_WEEK.items():
            scripted = [g for g in SCRIPTED_GAPS if g.service_id == service]
            plan = [g for g in scripted for _ in range(g.cases_in_week(week))]
            for index in range(count):
                gap = plan[index] if index < len(plan) else None
                row, row_answers = _case(rng, service, start, week, gap, weeks)
                cases.append(row)
                answers.extend(row_answers)
                if gap is not None:
                    negatives.append(_negative(row, gap, start))
    session.execute(insert(Case), cases)
    session.execute(insert(CaseAnswer), answers)
    grouping = group_into_gaps(negatives, national_owners=NATIONAL_OWNERS)
    intervention_at = _at(_week_start(today, weeks, INTERVENTION_WEEK), APPROVAL_HOUR)
    interventions = 0
    for proposal in grouping.gaps:
        interventions += _save_gap(session, proposal, intervention_at)
    return _summary(seed, weeks, cases, grouping.gaps, interventions)


def _case(
    rng: random.Random,
    service: str,
    start: date,
    week: int,
    gap: ScriptedGap | None,
    weeks: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    profile = case_profile(rng, service)
    case_id = _uuid(rng)
    outcome, cause, requirement = "ok", None, None
    if gap is not None:
        outcome, cause, requirement = "missing", gap.cause.value, gap.requirement_id
        office = gap.office_id or profile.office_id
    else:
        office = profile.office_id
        if rng.random() < other_failure_rate(service, week, INTERVENTION_WEEK):
            outcome = "other"
        if rng.random() < NO_REPLY_RATE:
            outcome = "none"
    replied = outcome != "none"
    row = {
        "id": case_id,
        "created_at": _at(start - timedelta(days=rng.randint(3, 12)), 10),
        "service_id": service,
        "variant": profile.variant,
        "category": profile.category,
        "language": profile.language,
        "office_id": office,
        "appointment_week": start,
        "deadline_days": profile.deadline_days,
        "outcome": outcome if replied else None,
        "cause": cause,
        "missing_requirement_id": requirement,
        "closed_in_time": (outcome == "ok") if replied else None,
        "rating": rng.randint(3, 5)
        if outcome == "ok"
        else (rng.randint(1, 3) if replied else None),
        "outcome_at": _at(start + timedelta(days=rng.randint(1, 4)), 12) if replied else None,
        "contact_ref": None,
        "synthetic": True,
    }
    rows = [{"case_id": case_id, "question_id": q, "answer": a} for q, a in profile.answers]
    return row, rows


def _negative(row: dict[str, Any], gap: ScriptedGap, week: date) -> NegativeOutcome:
    return NegativeOutcome(
        case_id=row["id"],
        service_id=gap.service_id,
        source_id=gap.source_id,
        cause=gap.cause,
        requirement_id=gap.requirement_id,
        office_id=row["office_id"],
        week=week,
    )


def _save_gap(session: Session, proposal: GapProposal, intervention_at: datetime) -> int:
    """Salva una lacuna; per la lacuna principale registra anche l'intervento."""
    scripted = next(g for g in SCRIPTED_GAPS if g.key == _key(proposal))
    count = len(proposal.case_ids)
    draft = None
    if count >= K_THRESHOLD:
        draft = draft_correction(
            GapForDraft(
                service_id=proposal.service_id,
                service_title=scripted.service_title,
                source_id=proposal.source_id,
                page_title=scripted.page_title,
                cause=proposal.cause.value,
                requirement_id=proposal.requirement_id,
                requirement_label=scripted.requirement_label,
                case_count=count,
            )
        )
    is_main = scripted.key == MAIN_GAP_KEY
    now = datetime.now(UTC)
    session.execute(
        insert(Gap).values(
            id=proposal.id,
            service_id=proposal.service_id,
            cause=proposal.cause.value,
            source_id=proposal.source_id,
            title=scripted.title,
            summary=proposal.summary,
            examples=proposal.examples,
            status="corretta" if is_main else scripted.status,
            recipient=proposal.recipient,
            owner_ente=proposal.owner_ente,
            requirement_id=proposal.requirement_id,
            draft_it=draft.it if draft else None,
            draft_easy_it=draft.easy_it if draft else None,
            draft_en=draft.en if draft else None,
            case_count=count,
            first_seen=_at(proposal.first_week, 12),
            last_seen=_at(proposal.last_week + timedelta(days=4), 12),
            synthetic=True,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        insert(GapCase), [{"gap_id": proposal.id, "case_id": c} for c in proposal.case_ids]
    )
    if not is_main or draft is None or scripted.requirement_text_it is None:
        return 0
    # L'intervento finisce nella checklist del cittadino: testo del requisito, non la
    # bozza per la redazione ("Pagina da modificare: ...") che resta solo sulla lacuna.
    session.execute(
        insert(Intervention).values(
            id=uuid.uuid5(proposal.id, "intervento"),
            gap_id=proposal.id,
            service_id=proposal.service_id,
            requirement_id=proposal.requirement_id,
            text_it=scripted.requirement_text_it,
            text_easy_it=scripted.requirement_text_it,
            text_en=scripted.requirement_text_en,
            approved_by=DEMO_APPROVER,
            approved_at=intervention_at,
        )
    )
    return 1


def _key(p: GapProposal) -> tuple[str, str, str | None]:
    return (p.service_id, p.cause.value, p.requirement_id)


def _summary(
    seed: int, weeks: int, cases: list[dict[str, Any]], gaps: list[GapProposal], interventions: int
) -> DemoSummary:
    main = next(g for g in gaps if _key(g) == MAIN_GAP_KEY)
    main_ids = set(main.case_ids)
    starts = sorted({c["appointment_week"] for c in cases})
    main_weeks = [c["appointment_week"] for c in cases if c["id"] in main_ids]
    by_week = [main_weeks.count(s) for s in starts]
    return DemoSummary(
        seed=seed,
        weeks=weeks,
        cases=len(cases),
        cases_with_outcome=sum(1 for c in cases if c["outcome"] is not None),
        gaps=len(gaps),
        gaps_above_threshold=sum(1 for g in gaps if len(g.case_ids) >= K_THRESHOLD),
        interventions=interventions,
        main_gap_cases_by_week=by_week,
        threshold_week=threshold_week(by_week, k=K_THRESHOLD),
        intervention_week=INTERVENTION_WEEK,
    )
