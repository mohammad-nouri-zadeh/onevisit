"""Template Jinja2 del gateway e scelta della lingua (storie B6, C7)."""

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from gateway.deps import GatewayDeps

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


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
