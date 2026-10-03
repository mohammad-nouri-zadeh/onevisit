"""Dipendenze FastAPI del pannello: dati e client Claude creati alla prima richiesta."""

from fastapi import HTTPException, Request, status

from dashboard.config import Settings
from dashboard.data import PanelData, SqlPanelData
from onevisit_analytics import AnthropicTextClient, TextClient
from onevisit_db.engine import create_db_engine, create_session_factory


def get_panel_data(request: Request) -> PanelData:
    """Dati del pannello; il database si apre solo qui (avvio senza variabili d'ambiente)."""
    state = request.app.state
    if state.panel_data is None:
        factory = state.session_factory
        if factory is None:
            settings: Settings = state.settings
            if not settings.database_url:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE, detail="database non configurato"
                )
            factory = create_session_factory(create_db_engine(settings.database_url))
        state.panel_data = SqlPanelData(factory)
    data: PanelData = state.panel_data
    return data


def get_claude_client(request: Request) -> TextClient | None:
    """Client Claude per la sintesi; ``None`` senza chiave API (testo da regola)."""
    state = request.app.state
    if state.claude_client is None and state.settings.anthropic_api_key:
        state.claude_client = AnthropicTextClient(state.settings.anthropic_api_key)
    client: TextClient | None = state.claude_client
    return client
