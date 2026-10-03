"""Costruzione delle dipendenze del gateway a partire dalle impostazioni (storia C5)."""

import importlib
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast

from gateway.config import Settings
from gateway.dispatcher import Cipher, Renderer, RetryPolicy, Senders
from gateway.inbound import RecentIds
from gateway.personal_links import LinkBuilder
from gateway.store import NotifierStore, sql_store_factory
from onevisit_channels import (
    EmailSender,
    FakeSmsProvider,
    LinkSigner,
    SmsProvider,
    SmtpEmailSender,
    TwilioSmsProvider,
    render_notification,
    resolve_link_signing_key,
)

logger = logging.getLogger(__name__)

# Quanti MessageSid ricordare per scartare i doppioni del fornitore.
RECENT_MESSAGE_IDS = 1000

StoreFactory = Callable[[], AbstractContextManager[NotifierStore]]


@dataclass
class GatewayDeps:
    """Tutto cio' che le rotte e il ciclo di invio usano."""

    settings: Settings
    sms: SmsProvider
    fake_sms: FakeSmsProvider | None
    email: EmailSender | None
    links: LinkBuilder
    signer: LinkSigner
    cipher: Cipher | None
    store_factory: StoreFactory | None
    renderer: Renderer
    retry: RetryPolicy
    recent_ids: RecentIds

    @property
    def senders(self) -> Senders:
        """Canali di uscita per il dispatcher."""
        return Senders(sms=self.sms, email=self.email)


def _build_cipher(settings: Settings) -> Cipher | None:
    if not (settings.encryption_key and settings.hmac_key):
        return None
    # Import ritardato: onevisit_privacy e' scritto in parallelo da un altro gruppo.
    module: Any = importlib.import_module("onevisit_privacy")
    return cast(Cipher, module.ContactCipher(settings.encryption_key, settings.hmac_key))


def _build_store_factory(settings: Settings) -> StoreFactory | None:
    if not settings.database_url:
        return None
    from onevisit_db.engine import create_db_engine, create_session_factory

    sessions = create_session_factory(create_db_engine(settings.database_url))
    return cast(StoreFactory, sql_store_factory(sessions))


def build_deps(settings: Settings) -> GatewayDeps:
    """Crea fornitori, firma dei link, cifratura e accesso al database."""
    fake_sms: FakeSmsProvider | None = None
    sms: SmsProvider
    if settings.uses_twilio:
        sms = TwilioSmsProvider(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
            from_number=settings.sms_from,
        )
    else:
        fake_sms = FakeSmsProvider()
        sms = fake_sms
    email = SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        sender=settings.email_from,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=settings.smtp_starttls,
    )
    # Fuori sviluppo senza chiave solleva LinkError: il gateway non parte (fail closed).
    signer = LinkSigner(
        resolve_link_signing_key(settings.link_signing_key, environment=settings.environment)
    )
    if not settings.link_signing_key:
        logger.warning("ONEVISIT_LINK_SIGNING_KEY mancante: chiave di sviluppo condivisa in uso")
    return GatewayDeps(
        settings=settings,
        sms=sms,
        fake_sms=fake_sms,
        email=email,
        links=LinkBuilder(signer, settings.assistant_base_url, settings.gateway_base_url),
        signer=signer,
        cipher=_build_cipher(settings),
        store_factory=_build_store_factory(settings),
        renderer=cast(Renderer, render_notification),
        retry=RetryPolicy(
            attempts=settings.send_attempts, base_delay_s=settings.retry_base_delay_s
        ),
        recent_ids=RecentIds(RECENT_MESSAGE_IDS),
    )
