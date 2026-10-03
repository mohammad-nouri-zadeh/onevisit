"""Interfaccia unica dei canali e adattatori web, email, SMS (storia C5).

L'agente non conosce il fornitore: riceve ``InboundMessage`` e le capacita' del canale.
"""

from collections.abc import Mapping
from typing import Protocol

from onevisit_channels.email import EmailSender
from onevisit_channels.errors import ChannelError
from onevisit_channels.models import ChannelCapabilities, InboundMessage, OutboundMessage
from onevisit_channels.sms import SmsProvider

# Lunghezza massima di un SMS in uscita: due segmenti GSM-7 concatenati.
SMS_MAX_CHARS = 306

WEB_CAPABILITIES = ChannelCapabilities(
    channel="web", full_conversation=True, buttons=True, max_chars=None, proactive=False
)
EMAIL_CAPABILITIES = ChannelCapabilities(
    channel="email", full_conversation=False, buttons=True, max_chars=None, proactive=True
)
SMS_CAPABILITIES = ChannelCapabilities(
    channel="sms", full_conversation=False, buttons=False, max_chars=SMS_MAX_CHARS, proactive=True
)


class ChannelAdapter(Protocol):
    """Contratto comune a tutti i canali."""

    @property
    def capabilities(self) -> ChannelCapabilities:
        """Capacita' del canale."""
        ...

    def parse_inbound(self, request: Mapping[str, str]) -> InboundMessage:
        """Trasforma i campi della richiesta del fornitore in un ``InboundMessage``."""
        ...

    async def send(self, message: OutboundMessage) -> None:
        """Spedisce un messaggio gia' composto."""
        ...


class SmsAdapter:
    """Adattatore SMS: campi in stile Twilio (``From``, ``Body``, ``MessageSid``)."""

    def __init__(self, provider: SmsProvider) -> None:
        self._provider = provider

    @property
    def capabilities(self) -> ChannelCapabilities:
        """Capacita' dell'SMS."""
        return SMS_CAPABILITIES

    def parse_inbound(self, request: Mapping[str, str]) -> InboundMessage:
        """Legge mittente, testo e identificativo del messaggio."""
        sender = request.get("From", "")
        if not sender:
            raise ChannelError("mittente mancante")
        return InboundMessage(
            channel="sms",
            sender=sender,
            text=request.get("Body", ""),
            provider_message_id=request.get("MessageSid") or None,
        )

    async def send(self, message: OutboundMessage) -> None:
        """Spedisce tramite il fornitore."""
        await self._provider.send(message.to, message.text)


class EmailAdapter:
    """Adattatore email: si usa solo in uscita; le risposte arrivano dai link firmati."""

    def __init__(self, sender: EmailSender) -> None:
        self._sender = sender

    @property
    def capabilities(self) -> ChannelCapabilities:
        """Capacita' dell'email."""
        return EMAIL_CAPABILITIES

    def parse_inbound(self, request: Mapping[str, str]) -> InboundMessage:
        """Le email in arrivo non sono gestite: si risponde con i link."""
        raise ChannelError("le email in arrivo non sono gestite")

    async def send(self, message: OutboundMessage) -> None:
        """Spedisce l'email con ``List-Unsubscribe``."""
        if message.subject is None or message.unsubscribe_url is None:
            raise ChannelError("email senza oggetto o senza link dei consensi")
        await self._sender.send(
            to=message.to,
            subject=message.subject,
            text=message.text,
            html=message.html,
            unsubscribe_url=message.unsubscribe_url,
        )


class WebAdapter:
    """Adattatore web: la chat risponde nella stessa richiesta HTTP."""

    @property
    def capabilities(self) -> ChannelCapabilities:
        """Capacita' della chat web."""
        return WEB_CAPABILITIES

    def parse_inbound(self, request: Mapping[str, str]) -> InboundMessage:
        """Legge il campo ``message`` del form della chat."""
        return InboundMessage(channel="web", sender="web", text=request.get("message", ""))

    async def send(self, message: OutboundMessage) -> None:
        """La chat web non invia in modo proattivo."""
        raise ChannelError("la chat web non invia messaggi proattivi")
