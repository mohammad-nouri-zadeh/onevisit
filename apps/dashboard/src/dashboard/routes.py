"""Rotte del pannello: accesso, panoramica, lacune, approvazione (storie C12, B10, B11, B13).

Le altre pagine (segnalazioni, interventi, sintesi, contesto, impostazioni) stanno in
``routes_more.py``. Ogni rotta che usa il database e' ``def`` (thread pool).
"""

import uuid
from typing import Annotated, Any, get_args

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dashboard.auth import COOKIE_NAME, ROLES, Role, current_role, require
from dashboard.data import PanelData
from dashboard.deps import get_panel_data
from dashboard.routes_more import router as more_router
from dashboard.views import rate_by, rate_by_service, weekly_series
from onevisit_analytics import CAUSES
from onevisit_db.repo import GapStatus

router = APIRouter()
router.include_router(more_router)

RoleDep = Annotated[Role, Depends(current_role)]
DataDep = Annotated[PanelData, Depends(get_panel_data)]
GAP_STATUSES: tuple[str, ...] = get_args(GapStatus)
EDITOR_ROLES: tuple[Role, ...] = ("redazione",)


def render(request: Request, name: str, role: Role | None, **context: Any) -> HTMLResponse:
    """Rende un template con il ruolo e la configurazione comuni."""
    templates = request.app.state.templates
    response: HTMLResponse = templates.TemplateResponse(
        request, name, {"role": role, "roles": ROLES, **context}
    )
    return response


def k_threshold(request: Request, data: PanelData) -> int:
    """Soglia k da analytics.config, con riserva nelle impostazioni."""
    value = data.config().get("k_threshold", request.app.state.settings.k_threshold)
    return int(value)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    """Pagina di accesso dimostrativo: si sceglie un ruolo."""
    return render(request, "login.html", None)


@router.post("/login")
def login(request: Request, role: Annotated[str, Form()]) -> Response:
    """Salva il ruolo scelto in un cookie firmato."""
    chosen = next((r for r in ROLES if r == role), None)
    if chosen is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="ruolo sconosciuto")
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        COOKIE_NAME,
        request.app.state.role_signer.sign(chosen),
        httponly=True,
        samesite="lax",
        max_age=request.app.state.settings.role_cookie_max_age_s,
    )
    return response


@router.post("/logout")
def logout() -> Response:
    """Cancella il cookie del ruolo."""
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/", response_class=HTMLResponse)
def overview(request: Request, role: RoleDep, data: DataDep) -> HTMLResponse:
    """Panoramica: tasso al primo appuntamento, lacune per causa, visite evitate."""
    rates = data.first_visit_rate()
    weekly = data.weekly_first_visit()
    config = data.config()
    cost = config.get("cost_per_slot_eur", request.app.state.settings.cost_per_slot_eur)
    return render(
        request,
        "overview.html",
        role,
        by_service=rate_by_service(weekly),
        by_language=rate_by(rates, "language"),
        by_category=rate_by(rates, "category"),
        weekly=weekly,
        weekly_chart=weekly_series(weekly),
        causes=data.gaps_by_cause(),
        avoided=data.avoided_visits(),
        cost_per_slot=cost,
        k=k_threshold(request, data),
    )


@router.get("/gaps", response_class=HTMLResponse)
def gaps(
    request: Request,
    role: RoleDep,
    data: DataDep,
    cause: str | None = None,
    service: str | None = None,
    gap_status: Annotated[str | None, Query(alias="status")] = None,
) -> HTMLResponse:
    """Lacune filtrabili, ordinate per numero di casi; sezione separata sotto soglia."""
    chosen_status = next((s for s in get_args(GapStatus) if s == gap_status), None)
    rows = data.list_gaps(cause=cause or None, service_id=service or None, status=chosen_status)
    k = k_threshold(request, data)
    every = data.list_gaps(cause=None, service_id=None, status=None)
    return render(
        request,
        "gaps.html",
        role,
        above=[g for g in rows if g.case_count >= k],
        below=[g for g in rows if g.case_count < k],
        k=k,
        causes=CAUSES,
        services=sorted({g.service_id for g in every}),
        statuses=GAP_STATUSES,
        selected={"cause": cause or "", "service": service or "", "status": gap_status or ""},
    )


@router.get("/gaps/{gap_id}", response_class=HTMLResponse)
def gap_detail(request: Request, gap_id: uuid.UUID, role: RoleDep, data: DataDep) -> HTMLResponse:
    """Dettaglio della lacuna con le tre bozze; registra l'accesso."""
    gap = data.get_gap(gap_id)
    if gap is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="lacuna inesistente")
    data.log_access(role=role, action="view_gap", object_id=str(gap_id))
    k = k_threshold(request, data)
    if gap.case_count < k:
        # Sotto soglia (C11): il server toglie numero, riassunto, esempi e date, cosi'
        # nessun dettaglio di un gruppo piccolo arriva al browser.
        gap = gap.model_copy(
            update={
                "case_count": 0,
                "summary": None,
                "examples": [],
                "first_seen": None,
                "last_seen": None,
            }
        )
    return render(
        request,
        "gap_detail.html",
        role,
        gap=gap,
        k=k,
        can_edit=role in EDITOR_ROLES,
    )


@router.post("/gaps/{gap_id}/approve")
def approve(
    gap_id: uuid.UUID,
    role: RoleDep,
    data: DataDep,
    text_it: Annotated[str, Form()],
    text_easy_it: Annotated[str, Form()] = "",
    text_en: Annotated[str, Form()] = "",
) -> Response:
    """Approva la bozza (solo redazione): intervento, stato corretta, registro accessi."""
    require(role, EDITOR_ROLES)
    if data.get_gap(gap_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="lacuna inesistente")
    data.approve_gap(gap_id, role=role, text_it=text_it, text_easy_it=text_easy_it, text_en=text_en)
    return RedirectResponse(f"/gaps/{gap_id}?approvata=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/gaps/{gap_id}/archive")
def archive(
    gap_id: uuid.UUID, role: RoleDep, data: DataDep, reason: Annotated[str, Form()]
) -> Response:
    """Archivia la lacuna con una motivazione (solo redazione)."""
    require(role, EDITOR_ROLES)
    data.archive_gap(gap_id, role=role, reason=reason)
    return RedirectResponse(f"/gaps/{gap_id}", status_code=status.HTTP_303_SEE_OTHER)
