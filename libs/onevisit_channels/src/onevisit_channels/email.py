"""Invio delle email con aiosmtplib e versione finta per i test (storia C7).

Ogni email ha testo semplice, HTML e l'intestazione ``List-Unsubscribe`` con il link
per gestire i consensi. Indirizzi e contenuti non finiscono mai nei log.
"""

from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from onevisit_channels.errors import ChannelSendError

# Tempo massimo di una sessione SMTP, in secondi.
DEFAULT_SMTP_TIMEOUT_S = 15.0


class EmailSender(Protocol):
    """Chi spedisce email: SMTP in esercizio, memoria nei test."""

    async def send(
        self, *, to: str, subject: str, text: str, html: str | None, unsubscribe_url: str
    ) -> None:
        """Spedisce un'email con versione testo e, se presente, HTML."""
        ...


def build_email(
    *, sender: str, to: str, subject: str, text: str, html: str | None, unsubscribe_url: str
) -> EmailMessage:
    """Compone il messaggio MIME con ``List-Unsubscribe``."""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    message.set_content(text)
    if html is not None:
        message.add_alternative(html, subtype="html")
    return message


@dataclass(frozen=True)
class SentEmail:
    """Email catturata dal mittente finto."""

    to: str
    subject: str
    text: str
    html: str | None
    unsubscribe_url: str


@dataclass
class FakeEmailSender:
    """Mittente finto: registra in memoria e puo' simulare guasti."""

    fail_times: int = 0
    always_fail: bool = False
    sent: list[SentEmail] = field(default_factory=list)
    attempts: int = 0

    async def send(
        self, *, to: str, subject: str, text: str, html: str | None, unsubscribe_url: str
    ) -> None:
        """Registra l'email o simula un guasto."""
        self.attempts += 1
        if self.always_fail or self.attempts <= self.fail_times:
            raise ChannelSendError("invio email simulato fallito")
        self.sent.append(SentEmail(to, subject, text, html, unsubscribe_url))


class SmtpEmailSender:
    """Mittente SMTP (Mailpit in sviluppo)."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        username: str | None = None,
        password: str | None = None,
        start_tls: bool = False,
        timeout_s: float = DEFAULT_SMTP_TIMEOUT_S,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._username = username or None
        self._password = password or None
        self._start_tls = start_tls
        self._timeout_s = timeout_s

    async def send(
        self, *, to: str, subject: str, text: str, html: str | None, unsubscribe_url: str
    ) -> None:
        """Spedisce; ogni errore diventa :class:`ChannelSendError` senza dati personali."""
        message = build_email(
            sender=self._sender,
            to=to,
            subject=subject,
            text=text,
            html=html,
            unsubscribe_url=unsubscribe_url,
        )
        try:
            await aiosmtplib.send(
                message,
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                start_tls=self._start_tls,
                timeout=self._timeout_s,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            raise ChannelSendError(f"invio SMTP fallito: {type(exc).__name__}") from None
