"""Modelli dei messaggi che attraversano il gateway dei canali (storia C5)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

ChannelName = Literal["web", "email", "sms"]

# Tipi di notifica salvati in core.notifications (docs/contracts.md, sezione 4).
NotificationKind = Literal[
    "reminder",
    "followup",
    "followup_nudge",
    "correction_notice",
    "revocation_confirm",
    "email_confirm",
]

# Tutti i modelli di messaggio: le notifiche piu' le risposte agli SMS in arrivo.
MessageKind = Literal[
    "reminder",
    "followup",
    "followup_nudge",
    "correction_notice",
    "revocation_confirm",
    "email_confirm",
    "help",
    "outcome_thanks",
    "unrecognized",
]

MESSAGE_KINDS: tuple[MessageKind, ...] = (
    "reminder",
    "followup",
    "followup_nudge",
    "correction_notice",
    "revocation_confirm",
    "email_confirm",
    "help",
    "outcome_thanks",
    "unrecognized",
)

SUPPORTED_LANGUAGES: tuple[str, ...] = ("it", "en")


class ChannelCapabilities(BaseModel):
    """Cosa sa fare un canale: l'agente adatta le risposte a questi limiti."""

    model_config = ConfigDict(frozen=True)

    channel: ChannelName
    full_conversation: bool
    buttons: bool
    max_chars: int | None
    proactive: bool


class InboundMessage(BaseModel):
    """Messaggio in arrivo. ``text`` vive solo in memoria e non si salva mai."""

    model_config = ConfigDict(frozen=True)

    channel: ChannelName
    sender: str
    text: str
    provider_message_id: str | None = None


class OutboundMessage(BaseModel):
    """Messaggio in uscita, gia' composto dai modelli."""

    model_config = ConfigDict(frozen=True)

    channel: ChannelName
    to: str
    text: str
    subject: str | None = None
    html: str | None = None
    unsubscribe_url: str | None = None


class RenderedMessage(BaseModel):
    """Risultato di :func:`render_notification`."""

    model_config = ConfigDict(frozen=True)

    subject: str | None
    text: str
    html: str | None


class SmsReply(BaseModel):
    """Risposta del cittadino a un SMS, ridotta a una delle parole chiave."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["1", "2", "3", "STOP", "AIUTO", "other"]
