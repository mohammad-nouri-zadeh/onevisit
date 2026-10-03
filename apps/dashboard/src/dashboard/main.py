"""Punto di ingresso ASGI di dashboard.

Avvio: ``uvicorn dashboard.main:app``. Le rotte applicative vanno aggiunte
in moduli dedicati e registrate in :func:`create_app`.
"""

from fastapi import FastAPI

from dashboard.config import get_settings


def create_app() -> FastAPI:
    """Crea l'applicazione FastAPI con le rotte di base."""
    settings = get_settings()
    app = FastAPI(title="OneVisit · Dashboard", version="0.1.0")

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, str]:
        """Controllo di salute usato da Docker e dal reverse proxy."""
        return {"status": "ok", "service": settings.service_name}

    return app


app = create_app()
