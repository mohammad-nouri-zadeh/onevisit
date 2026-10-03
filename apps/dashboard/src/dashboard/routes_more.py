"""Rotte del pannello: segnalazioni, interventi, sintesi, contesto, impostazioni (B12, B13)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dashboard.auth import ROLES, Role, current_role, require
from dashboard.city_context import read_context
from dashboard.data import PanelData
from dashboard.deps import get_claude_client, get_panel_data
from dashboard.views import weekly_data
from onevisit_analytics import TextClient, weekly_summary
from onevisit_db.repo import MIN_K_THRESHOLD

router = APIRouter()
RoleDep = Annotated[Role, Depends(current_role)]
DataDep = Annotated[PanelData, Depends(get_panel_data)]
ClientDep = Annotated[TextClient | None, Depends(get_claude_client)]
SETTINGS_ROLES: tuple[Role, ...] = ("direzione",)
# Finestra di riserva (settimane) se analytics.config non la contiene.
DEFAULT_WINDOW_WEEKS = 4
# Chiavi di analytics.config modificabili dalla direzione.
CONFIG_KEYS = ("k_threshold", "cost_per_slot_eur", "window_weeks")


def _render(request: Request, name: str, role: Role, **context: Any) -> HTMLResponse:
    response: HTMLResponse = request.app.state.templates.TemplateResponse(
        request, name, {"role": role, "roles": ROLES, **context}
    )
    return response


def _k(request: Request, data: PanelData) -> int:
    return int(data.config().get("k_threshold", request.app.state.settings.k_threshold))


@router.get("/office", response_class=HTMLResponse)
def office_reports(request: Request, role: RoleDep, data: DataDep) -> HTMLResponse:
    """Segnalazioni aggregate per procedura, solo lacune sopra soglia; mai date o dipendenti."""
    k = _k(request, data)
    rows = [
        g
        for g in data.list_gaps(cause=None, service_id=None, status=None)
        if g.case_count >= k and g.status != "archiviata"
    ]
    services = sorted({g.service_id for g in rows})
    grouped = {s: [g for g in rows if g.service_id == s] for s in services}
    window = int(data.config().get("window_weeks", DEFAULT_WINDOW_WEEKS))
    return _render(request, "office.html", role, grouped=grouped, k=k, window=window)


@router.get("/interventions", response_class=HTMLResponse)
def interventions(request: Request, role: RoleDep, data: DataDep) -> HTMLResponse:
    """Interventi approvati con il tasso prima e dopo e il numero di casi."""
    return _render(
        request, "interventions.html", role, effects=data.intervention_effect(), k=_k(request, data)
    )


@router.get("/summary", response_class=HTMLResponse)
def summary(request: Request, role: RoleDep, data: DataDep, client: ClientDep) -> HTMLResponse:
    """Sintesi settimanale dalle sole viste aggregate."""
    k = _k(request, data)
    payload = weekly_data(
        data.weekly_first_visit(), data.gaps_by_cause(), data.intervention_effect(), k_threshold=k
    )
    model = request.app.state.settings.model_conversation
    text = weekly_summary(payload, client=client, model=model)
    return _render(request, "summary.html", role, text=text, by_claude=client is not None)


@router.get("/context", response_class=HTMLResponse)
def city_context(request: Request, role: RoleDep) -> HTMLResponse:
    """Statistiche del Comune che spiegano il problema (dataset aperti)."""
    tables = read_context(request.app.state.settings.data_dir)
    return _render(request, "context.html", role, tables=tables)


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, role: RoleDep, data: DataDep) -> HTMLResponse:
    """Parametri delle metriche (solo direzione)."""
    require(role, SETTINGS_ROLES)
    return _render(request, "settings.html", role, config=data.config(), keys=CONFIG_KEYS)


@router.post("/settings")
def save_settings(
    role: RoleDep,
    data: DataDep,
    # Mai sotto 5 (C11): lo impone anche il vincolo su analytics.config (migrazione 0003).
    k_threshold: Annotated[int, Form(ge=MIN_K_THRESHOLD)],
    cost_per_slot_eur: Annotated[float, Form(ge=0)],
    window_weeks: Annotated[int, Form(ge=1)],
) -> Response:
    """Salva i parametri in analytics.config (solo direzione)."""
    require(role, SETTINGS_ROLES)
    data.set_config("k_threshold", k_threshold, role=role)  # repo rifiuta k < 5
    data.set_config("cost_per_slot_eur", cost_per_slot_eur, role=role)
    data.set_config("window_weeks", window_weeks, role=role)
    return RedirectResponse("/settings?salvato=1", status_code=status.HTTP_303_SEE_OTHER)
