"""Configurazione del pannello, letta dalle variabili d'ambiente (storia C12).

Ogni applicazione possiede la propria configurazione. Le librerie in ``libs/``
non leggono l'ambiente: ricevono i valori come parametri. Importare questo modulo
non richiede alcuna variabile: i default permettono l'avvio in sviluppo.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Impostazioni del pannello."""

    model_config = SettingsConfigDict(env_prefix="ONEVISIT_", extra="ignore")

    service_name: str = "dashboard"
    environment: str = "development"
    # URL con il ruolo app_dashboard (legge solo analytics, core.gaps, core.interventions).
    database_url: str = ""
    # Cartella del livello dati del team (statistiche in data/context/*.csv).
    data_dir: Path = Path("/app/data")
    # Segreto per firmare il cookie del ruolo dimostrativo; vuoto = casuale per processo.
    session_secret: str = ""
    # Soglia k di riserva se analytics.config non la contiene.
    k_threshold: int = 5
    # Costo per slot di riserva (euro) se analytics.config non lo contiene.
    cost_per_slot_eur: float = 0.0
    # Chiave Claude per la sintesi settimanale; vuota = testo da regola.
    anthropic_api_key: str = Field(
        default="", validation_alias=AliasChoices("ANTHROPIC_API_KEY", "ONEVISIT_ANTHROPIC_API_KEY")
    )
    model_conversation: str = "claude-sonnet-5-5"
    # Durata del cookie del ruolo dimostrativo, in secondi (8 ore).
    role_cookie_max_age_s: int = 8 * 3600


@lru_cache
def get_settings() -> Settings:
    """Restituisce le impostazioni, lette una sola volta per processo."""
    return Settings()
