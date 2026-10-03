"""Configurazione del gateway, letta dalle variabili d'ambiente (storie C5-C8).

Ogni applicazione possiede la propria configurazione. Le librerie in ``libs/``
non leggono l'ambiente: ricevono i valori come parametri.
"""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Impostazioni di gateway (prefisso ``ONEVISIT_``)."""

    model_config = SettingsConfigDict(env_prefix="ONEVISIT_", extra="ignore")

    service_name: str = "gateway"
    environment: str = "development"
    database_url: str = ""
    # Modalita' demo: tempi compressi e pagina /demo/phone attiva.
    demo_mode: bool = False
    # In demo un giorno dura questi secondi (vedi .env.example).
    demo_seconds_per_day: int = 60
    reminder_days_before: int = 3
    timezone: str = "Europe/Rome"

    # Ciclo di invio delle notifiche: intervallo normale e in demo, in secondi.
    scheduler_enabled: bool = True
    dispatch_interval_s: float = 30.0
    dispatch_interval_demo_s: float = 5.0
    # Notifiche lette a ogni giro del ciclo.
    dispatch_batch_size: int = 50
    # Conservazione (C9): ogni quanto cancellare i contatti scaduti, in secondi (un giorno).
    retention_purge_interval_s: float = 86400.0
    # Tentativi per canale e attesa iniziale (raddoppia a ogni tentativo), in secondi.
    send_attempts: int = 3
    retry_base_delay_s: float = 1.0

    # Chiavi (32 byte base64) e firma dei link.
    encryption_key: str = ""
    hmac_key: str = ""
    link_signing_key: str = ""
    # Validita' dei link personali, in giorni.
    link_max_age_days: int = 60

    # URL pubbliche: assistente web (checklist, esito, consensi) e gateway (link di risposta).
    assistant_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices("ONEVISIT_ASSISTANT_BASE_URL", "ONEVISIT_PUBLIC_BASE_URL"),
    )
    gateway_base_url: str = "http://localhost:8002"

    # SMS: "twilio" o "fake". Senza credenziali Twilio si usa sempre il fornitore finto.
    sms_provider: Literal["twilio", "fake"] = "fake"
    twilio_account_sid: str = Field(
        default="",
        validation_alias=AliasChoices("ONEVISIT_TWILIO_ACCOUNT_SID", "TWILIO_ACCOUNT_SID"),
    )
    twilio_auth_token: str = Field(
        default="", validation_alias=AliasChoices("ONEVISIT_TWILIO_AUTH_TOKEN", "TWILIO_AUTH_TOKEN")
    )
    sms_from: str = ""

    # Email (Mailpit in sviluppo).
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    email_from: str = "OneVisit <noreply@example.org>"

    @property
    def uses_twilio(self) -> bool:
        """Vero se l'SMS passa da Twilio (e quindi la firma del webhook e' obbligatoria)."""
        return (
            self.sms_provider == "twilio"
            and bool(self.twilio_account_sid)
            and bool(self.twilio_auth_token)
        )

    @property
    def demo_pages_enabled(self) -> bool:
        """La pagina /demo/phone esiste solo in demo o in sviluppo."""
        return self.demo_mode or self.environment == "development"

    @property
    def dispatch_interval(self) -> float:
        """Intervallo del ciclo di invio, piu' corto in demo."""
        return self.dispatch_interval_demo_s if self.demo_mode else self.dispatch_interval_s


@lru_cache
def get_settings() -> Settings:
    """Restituisce le impostazioni, lette una sola volta per processo."""
    return Settings()
