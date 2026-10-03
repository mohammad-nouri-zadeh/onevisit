"""Configurazione di assistant_web, letta dalle variabili d'ambiente (storie B1-B5, B7-B9, B11).

Ogni applicazione possiede la propria configurazione. Le librerie in ``libs/``
non leggono l'ambiente: ricevono i valori come parametri.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Impostazioni di assistant_web (prefisso ``ONEVISIT_``)."""

    model_config = SettingsConfigDict(env_prefix="ONEVISIT_", extra="ignore", populate_by_name=True)

    service_name: str = "assistant_web"
    environment: str = "development"
    # URL SQLAlchemy con il ruolo app_assistant; vuota = funzioni con database disattivate.
    database_url: str = ""
    # Cartella del livello dati del team (catalogo, fonti, sedi).
    data_dir: Path = Path("/app/data")
    # Solo sviluppo: mostra anche i requisiti non verificati.
    include_drafts: bool = False

    model_conversation: str = "claude-sonnet-5-5"
    model_fast: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: str = Field(
        default="", validation_alias=AliasChoices("ANTHROPIC_API_KEY", "ONEVISIT_ANTHROPIC_API_KEY")
    )
    official_fallback_url: str = "https://www.comune.milano.it/servizi"

    # Chiavi (32 byte base64) per cifrare i contatti e calcolarne l'impronta.
    encryption_key: str = ""
    hmac_key: str = ""
    # Firma dei link personali e del cookie di sessione; vuote = chiave casuale per processo.
    link_signing_key: str = ""
    session_secret: str = ""

    # Modalita' demo: un giorno dura demo_seconds_per_day secondi per le notifiche.
    demo_mode: bool = False
    demo_seconds_per_day: int = 60
    reminder_days_before: int = 3
    # Giorni dopo i quali una fonte va riverificata (B3).
    source_stale_days: int = 30

    public_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices("ONEVISIT_PUBLIC_BASE_URL", "ONEVISIT_ASSISTANT_BASE_URL"),
    )
    gateway_base_url: str = "http://localhost:8002"

    # Durata della sessione di chat in memoria, in secondi (mai salvata su disco).
    session_ttl_s: int = 3600
    # Lunghezza massima di un messaggio del cittadino, in caratteri.
    max_message_chars: int = 2000
    # Validita' dei link personali (checklist, esito, consensi), in giorni.
    link_max_age_days: int = 60
    # Giorni dopo l'appuntamento oltre i quali il contatto viene cancellato.
    contact_retention_days: int = 30
    # Secondi minimi tra due ricarichi del catalogo con le correzioni approvate (B11).
    catalog_refresh_s: float = 30.0
    # Timeout e tentativi della chiamata a Claude che struttura il commento sull'esito:
    # la pagina dell'esito non deve restare appesa (il default dell'SDK e' 10 minuti).
    feedback_timeout_s: float = 20.0
    feedback_max_retries: int = 1


@lru_cache
def get_settings() -> Settings:
    """Restituisce le impostazioni, lette una sola volta per processo."""
    return Settings()
