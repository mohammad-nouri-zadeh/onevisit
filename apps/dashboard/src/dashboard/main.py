"""Punto di ingresso ASGI del pannello del Comune (storie C12, B10-B13).

Avvio: ``uvicorn dashboard.main:app``. Il database si apre alla prima richiesta che
ne ha bisogno, cosi' importare il modulo non richiede variabili d'ambiente.
"""

import logging
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker

import onevisit_ui
from dashboard.auth import RoleSigner
from dashboard.config import Settings, get_settings
from dashboard.routes import router
from onevisit_analytics import TextClient

logger = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).resolve().parent


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
    claude_client: TextClient | None = None,
) -> FastAPI:
    """Crea l'applicazione; ``session_factory`` e ``claude_client`` sostituibili nei test."""
    settings = settings or get_settings()
    app = FastAPI(title="OneVisit · Pannello del Comune", version="0.1.0")
    secret = settings.session_secret
    if not secret:
        logger.warning("ONEVISIT_SESSION_SECRET vuota: segreto casuale per questo processo")
        secret = secrets.token_urlsafe(32)
    app.state.settings = settings
    app.state.role_signer = RoleSigner(secret, max_age_s=settings.role_cookie_max_age_s)
    app.state.session_factory = session_factory
    app.state.panel_data = None
    app.state.claude_client = claude_client
    app.state.templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    app.mount(onevisit_ui.MOUNT_PATH, StaticFiles(directory=onevisit_ui.STATIC_DIR), name="ui")
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, str]:
        """Controllo di salute usato da Docker e dal reverse proxy."""
        return {"status": "ok", "service": settings.service_name}

    app.include_router(router)
    return app


app = create_app()
