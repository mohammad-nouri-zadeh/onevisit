"""Invio delle notifiche in scadenza (storie C8, B7, B9).

Prima di ogni invio ricontrolla consenso e contatto: se il consenso e' revocato o il
contatto non c'e' piu', la notifica si chiude come ``cancelled`` senza inviare nulla.
Tre tentativi con attesa crescente sul canale principale, poi quello di riserva, poi
``failed``. Nei log solo identificativi opachi: mai indirizzi, numeri o testi.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from gateway.personal_links import LinkBuilder
from gateway.store import ContactTarget, DueNotification, NotifierStore
from onevisit_channels import ChannelSendError, EmailSender, RenderedMessage, SmsProvider
from onevisit_privacy import DecryptionError

logger = logging.getLogger(__name__)

ROME = ZoneInfo("Europe/Rome")

# Consenso richiesto per ogni tipo di notifica (None: messaggio di servizio sempre ammesso).
CONSENT_FOR_KIND: dict[str, str | None] = {
    "reminder": "reminder",
    "followup": "followup",
    "followup_nudge": "followup",
    "correction_notice": "correction",
    "revocation_confirm": None,
    "email_confirm": None,
}


class Cipher(Protocol):
    """Parte di ``onevisit_privacy.ContactCipher`` usata dal gateway."""

    def decrypt(self, token: bytes) -> str: ...
    def digest(self, value: str) -> str: ...


class Renderer(Protocol):
    """Firma di ``onevisit_channels.render_notification``."""

    def __call__(
        self,
        kind: str,
        *,
        language: str,
        channel: str,
        days_left: int | None,
        link: str,
        consents_link: str | None = None,
    ) -> RenderedMessage: ...


@dataclass(frozen=True)
class Senders:
    """Canali di uscita configurati."""

    sms: SmsProvider | None = None
    email: EmailSender | None = None


@dataclass(frozen=True)
class RetryPolicy:
    """Tentativi per canale e attesa iniziale, che raddoppia a ogni tentativo."""

    attempts: int = 3
    base_delay_s: float = 1.0
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep


@dataclass
class DispatchReport:
    """Conteggi di un giro del ciclo (nessun dato personale)."""

    sent: int = 0
    failed: int = 0
    cancelled: int = 0
    ids: list[UUID] = field(default_factory=list)


def days_left(appointment_at: datetime | None, now: datetime, tz: ZoneInfo) -> int | None:
    """Giorni di calendario (ora di Roma) che mancano all'appuntamento."""
    if appointment_at is None:
        return None
    return max((appointment_at.astimezone(tz).date() - now.astimezone(tz).date()).days, 0)


def _usable_channels(row: DueNotification, target: ContactTarget, senders: Senders) -> list[str]:
    """Canale della notifica, poi quello di riserva, se hanno indirizzo e mittente."""
    ordered = [row.channel]
    for extra in (target.fallback_channel, target.preferred_channel):
        if extra and extra not in ordered:
            ordered.append(extra)
    usable: list[str] = []
    for channel in ordered:
        if channel == "sms" and target.phone_enc and senders.sms is not None:
            usable.append(channel)
        email_ok = target.confirmed or row.kind == "email_confirm"
        if channel == "email" and target.email_enc and email_ok and senders.email is not None:
            usable.append(channel)
    return usable[:2]


async def _send_once(
    channel: str, address: str, message: RenderedMessage, consents_link: str, senders: Senders
) -> None:
    if channel == "sms" and senders.sms is not None:
        await senders.sms.send(address, message.text)
        return
    if channel == "email" and senders.email is not None and message.subject is not None:
        await senders.email.send(
            to=address,
            subject=message.subject,
            text=message.text,
            html=message.html,
            unsubscribe_url=consents_link,
        )
        return
    raise ChannelSendError("canale non configurato")


async def _send_with_retry(
    send: Callable[[], Awaitable[None]], retry: RetryPolicy, notification_id: UUID, channel: str
) -> bool:
    for attempt in range(1, retry.attempts + 1):
        try:
            await send()
        except ChannelSendError as exc:
            logger.warning(
                "notifica %s: tentativo %d su %s fallito (%s)",
                notification_id,
                attempt,
                channel,
                exc,
            )
            if attempt < retry.attempts:
                await retry.sleep(retry.base_delay_s * 2 ** (attempt - 1))
        else:
            return True
    return False


@dataclass(frozen=True)
class DispatchContext:
    """Dipendenze di un giro del ciclo di invio."""

    senders: Senders
    renderer: Renderer
    links: LinkBuilder
    cipher: Cipher
    retry: RetryPolicy = RetryPolicy()
    timezone: ZoneInfo = ROME


async def _deliver(
    row: DueNotification, target: ContactTarget, ctx: DispatchContext, now: datetime
) -> str:
    """Prova i canali utilizzabili e restituisce lo stato finale della notifica."""
    channels = _usable_channels(row, target, ctx.senders)
    if not channels:
        return "cancelled"
    consents_link = ctx.links.consents(row.case_id, target.contact_id)
    for channel in channels:
        encrypted = target.phone_enc if channel == "sms" else target.email_enc
        if encrypted is None:
            continue
        try:
            address = ctx.cipher.decrypt(encrypted)
        except DecryptionError:
            # Contatto cifrato con un'altra chiave (per esempio dopo una rotazione): si prova
            # il canale successivo e, se nessuno funziona, la notifica risulta "failed".
            # Una notifica illeggibile non deve fermare l'invio di tutte le altre.
            logger.warning("notifica %s: contatto non decifrabile sul canale %s", row.id, channel)
            continue
        message = ctx.renderer(
            row.kind,
            language=target.language,
            channel=channel,
            days_left=days_left(target.appointment_at, now, ctx.timezone),
            link=ctx.links.for_kind(row.kind, channel, row.case_id, target.contact_id),
            consents_link=consents_link,
        )

        async def send(
            ch: str = channel, to: str = address, msg: RenderedMessage = message
        ) -> None:
            await _send_once(ch, to, msg, consents_link, ctx.senders)

        if await _send_with_retry(send, ctx.retry, row.id, channel):
            return "sent"
    return "failed"


def _allowed(row: DueNotification, target: ContactTarget | None) -> bool:
    if target is None:
        return False
    consent = CONSENT_FOR_KIND.get(row.kind)
    return consent is None or bool(target.consents.get(consent))


async def dispatch_due(
    store: NotifierStore, *, now: datetime, ctx: DispatchContext, limit: int = 50
) -> DispatchReport:
    """Invia le notifiche in scadenza e ne aggiorna lo stato, una per una."""
    report = DispatchReport()
    for row in store.due_notifications(now=now, limit=limit):
        target = store.target_for_case(row.case_id)
        if target is None or not _allowed(row, target):
            status = "cancelled"
        else:
            status = await _deliver(row, target, ctx, now)
        store.mark_notification(row.id, status=status)
        store.commit()
        setattr(report, status, getattr(report, status) + 1)
        report.ids.append(row.id)
        logger.info("notifica %s (%s): %s", row.id, row.kind, status)
    return report
