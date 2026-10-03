"""Interfaccia dei canali e adattatori web, email, SMS; modelli dei messaggi (C5-C7, B6-B9, A4).

API pubblica fissata in docs/contracts.md, sezione 5.
"""

from onevisit_channels.adapters import (
    EMAIL_CAPABILITIES,
    SMS_CAPABILITIES,
    SMS_MAX_CHARS,
    WEB_CAPABILITIES,
    ChannelAdapter,
    EmailAdapter,
    SmsAdapter,
    WebAdapter,
)
from onevisit_channels.email import EmailSender, FakeEmailSender, SentEmail, SmtpEmailSender
from onevisit_channels.errors import (
    ChannelError,
    ChannelSendError,
    LinkError,
    SignatureError,
    TemplateNotFoundError,
)
from onevisit_channels.gsm import is_gsm7, sms_segments
from onevisit_channels.links import (
    PURPOSE_CHECKLIST,
    PURPOSE_CONSENTS,
    PURPOSE_EMAIL_CONFIRM,
    PURPOSE_OUTCOME,
    PURPOSE_REPLY,
    LinkSigner,
    resolve_link_signing_key,
)
from onevisit_channels.models import (
    MESSAGE_KINDS,
    ChannelCapabilities,
    InboundMessage,
    MessageKind,
    NotificationKind,
    OutboundMessage,
    RenderedMessage,
    SmsReply,
)
from onevisit_channels.notice import informativa
from onevisit_channels.phone import normalize_phone
from onevisit_channels.render import render_notification
from onevisit_channels.schedule import plan_notifications
from onevisit_channels.sms import (
    FakeSmsProvider,
    SentSms,
    SmsProvider,
    TwilioSmsProvider,
    parse_sms_reply,
    twilio_signature,
    validate_twilio_signature,
)

__all__ = [
    "EMAIL_CAPABILITIES",
    "MESSAGE_KINDS",
    "PURPOSE_CHECKLIST",
    "PURPOSE_CONSENTS",
    "PURPOSE_EMAIL_CONFIRM",
    "PURPOSE_OUTCOME",
    "PURPOSE_REPLY",
    "SMS_CAPABILITIES",
    "SMS_MAX_CHARS",
    "WEB_CAPABILITIES",
    "ChannelAdapter",
    "ChannelCapabilities",
    "ChannelError",
    "ChannelSendError",
    "EmailAdapter",
    "EmailSender",
    "FakeEmailSender",
    "FakeSmsProvider",
    "InboundMessage",
    "LinkError",
    "LinkSigner",
    "MessageKind",
    "NotificationKind",
    "OutboundMessage",
    "RenderedMessage",
    "SentEmail",
    "SentSms",
    "SignatureError",
    "SmsAdapter",
    "SmsProvider",
    "SmsReply",
    "SmtpEmailSender",
    "TemplateNotFoundError",
    "TwilioSmsProvider",
    "WebAdapter",
    "informativa",
    "is_gsm7",
    "normalize_phone",
    "parse_sms_reply",
    "plan_notifications",
    "render_notification",
    "resolve_link_signing_key",
    "sms_segments",
    "twilio_signature",
    "validate_twilio_signature",
]
