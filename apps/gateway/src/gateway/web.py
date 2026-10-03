"""Template Jinja2 del gateway e scelta della lingua (storie B6, C7)."""

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

import onevisit_ui
from gateway.deps import GatewayDeps

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
# Fogli di stile del design system, nell'ordine (vedi libs/onevisit_ui).
TEMPLATES.env.globals["ui_stylesheets"] = [
    onevisit_ui.asset_url(name) for name in onevisit_ui.STYLESHEETS
]
#: Cartella dei file statici propri del gateway (poche regole sopra il design system).
STATIC_DIR = Path(__file__).parent / "static"


def page_language(request: Request) -> str:
    """Italiano se il browser lo chiede, altrimenti inglese."""
    if request.query_params.get("lang") in ("it", "en"):
        return str(request.query_params["lang"])
    accept = request.headers.get("accept-language", "it").lower()
    return "it" if accept.startswith("it") or not accept else "en"


def get_deps(request: Request) -> GatewayDeps:
    """Dipendenze salvate nello stato dell'applicazione."""
    deps: GatewayDeps = request.app.state.deps
    return deps
