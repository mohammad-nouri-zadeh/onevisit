"""Punto di ingresso ASGI di assistant_web (storie B1-B5, B7-B9, B11).

Avvio: ``uvicorn assistant_web.main:app``. ``create_app`` accetta finti per i test
(client Claude, caricatore del catalogo, factory delle sessioni, repo) e non apre
connessioni ne' carica il catalogo all'import.
"""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

import onevisit_ui
from assistant_web import routes_chat, routes_contact, routes_pages
from assistant_web.config import Settings, get_settings
from assistant_web.i18n import LANG_COOKIE, LANG_COOKIE_MAX_AGE_S, chosen_language
from assistant_web.runtime import CatalogLoader, Runtime, SessionFactory
from assistant_web.web import TEMPLATES, context
from onevisit_agent import ClaudeClient
from onevisit_privacy import ClaudeClient as FeedbackClient
from onevisit_privacy import PiiLogFilter

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    settings: Settings | None = None,
    *,
    claude_client: ClaudeClient | None = None,
    catalog_loader: CatalogLoader | None = None,
    session_factory: SessionFactory | None = None,
    repo: ModuleType | Any | None = None,
    feedback_client: FeedbackClient | None = None,
) -> FastAPI:
    """Crea l'applicazione FastAPI con le rotte della chat e delle pagine personali."""
    settings = settings or get_settings()
    app = FastAPI(title="OneVisit · Assistant web", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.runtime = Runtime(
        settings,
        claude_client=claude_client,
        catalog_loader=catalog_loader,
        session_factory=session_factory,
        repo=repo,
        feedback_client=feedback_client,
    )
    logging.getLogger("assistant_web").addFilter(PiiLogFilter())
    app.mount(onevisit_ui.MOUNT_PATH, StaticFiles(directory=onevisit_ui.STATIC_DIR), name="ui")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.middleware("http")
    async def remember_language(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Ricorda nel cookie la lingua scelta dal menu (``?lang=it|en``)."""
        response = await call_next(request)
        chosen = chosen_language(request.query_params.get("lang"), None)
        if chosen:
            response.set_cookie(
                LANG_COOKIE, chosen, max_age=LANG_COOKIE_MAX_AGE_S, samesite="lax", httponly=True
            )
        return response

    app.include_router(routes_chat.router)
    app.include_router(routes_contact.router)
    app.include_router(routes_pages.router)

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, str]:
        """Controllo di salute usato da Docker e dal reverse proxy."""
        return {"status": "ok", "service": settings.service_name}

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> Response:
        """Errore generico senza traccia ne' testo del cittadino nella risposta o nei log."""
        logger.error("errore non gestito su %s: %s", request.url.path, type(exc).__name__)
        return TEMPLATES.TemplateResponse(
            request, "message.html", context("it", key="error_generic"), status_code=500
        )

    return app


app = create_app()
