"""Configurazione del servizio, letta dalle variabili d'ambiente.

Ogni applicazione possiede la propria configurazione. Le librerie in ``libs/``
non leggono l'ambiente: ricevono i valori come parametri.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Impostazioni di gateway."""

    model_config = SettingsConfigDict(env_prefix="ONEVISIT_", extra="ignore")

    service_name: str = "gateway"
    environment: str = "development"
    database_url: str = ""


@lru_cache
def get_settings() -> Settings:
    """Restituisce le impostazioni, lette una sola volta per processo."""
    return Settings()
