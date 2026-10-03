"""Punto di ingresso ASGI di gateway (storie C5-C8, B6, B7, B9).

Avvio: ``uvicorn gateway.main:app``. Rotte: ``/health``, ``/sms/inbound``, ``/r/{token}``,
``/demo/phone``. Se il database e' configurato, il lifespan avvia il ciclo di invio
delle notifiche (vedi :mod:`gateway.scheduler`).
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gateway import routes_demo, routes_replies, routes_sms
from gateway.config import Settings, get_settings
from gateway.deps import GatewayDeps, build_deps
from gateway.scheduler import run_loop


def create_app(settings: Settings | None = None, deps: GatewayDeps | None = None) -> FastAPI:
    """Crea l'applicazione; nei test si passano impostazioni e dipendenze finte."""
    settings = settings or (deps.settings if deps is not None else get_settings())
    resolved = deps or build_deps(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        task: asyncio.Task[None] | None = None
        if settings.scheduler_enabled and settings.database_url and resolved.store_factory:
            task = asyncio.create_task(run_loop(resolved, stop))
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="OneVisit · Gateway", version="0.1.0", lifespan=lifespan)
    app.state.deps = resolved

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, str]:
        """Controllo di salute usato da Docker e dal reverse proxy."""
        return {"status": "ok", "service": settings.service_name}

    app.include_router(routes_sms.router)
    app.include_router(routes_replies.router)
    app.include_router(routes_demo.router)
    return app


app = create_app()
