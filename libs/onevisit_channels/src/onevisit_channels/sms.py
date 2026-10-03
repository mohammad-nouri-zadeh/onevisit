"""Fornitori SMS sostituibili e firma dei webhook (storie C6, B6).

Nessun tipo del fornitore esce da questo modulo: si scambiano solo stringhe.
I testi e i numeri non finiscono mai nei log ne' nei messaggi delle eccezioni.
"""

import base64
import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

import httpx

from onevisit_channels.errors import ChannelSendError
from onevisit_channels.models import SmsReply

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"
# Tempo massimo di attesa di una chiamata al fornitore, in secondi.
DEFAULT_TIMEOUT_S = 10.0

ReplyKind = Literal["1", "2", "3", "STOP", "AIUTO", "other"]

_REPLY_KEYWORDS: dict[str, ReplyKind] = {
    "1": "1",
    "2": "2",
    "3": "3",
    "STOP": "STOP",
    "STOPALL": "STOP",
    "UNSUBSCRIBE": "STOP",
    "ANNULLA": "STOP",
    "AIUTO": "AIUTO",
    "HELP": "AIUTO",
    "INFO": "AIUTO",
}


class SmsProvider(Protocol):
    """Fornitore SMS. ``send`` restituisce l'identificativo opaco del messaggio."""

    async def send(self, to: str, body: str) -> str:
        """Invia ``body`` al numero E.164 ``to``."""
        ...


@dataclass(frozen=True)
class SentSms:
    """SMS catturato dal fornitore finto (solo memoria, per test e demo)."""

    to: str
    body: str
    sent_at: datetime
    message_id: str


@dataclass
class FakeSmsProvider:
    """Fornitore finto: registra in memoria e puo' simulare guasti.

    ``fail_times`` fa fallire i primi N invii; ``always_fail`` li fa fallire tutti.
    """

    fail_times: int = 0
    always_fail: bool = False
    sent: list[SentSms] = field(default_factory=list)
    attempts: int = 0

    async def send(self, to: str, body: str) -> str:
        """Registra il messaggio, o solleva :class:`ChannelSendError` se simula un guasto."""
        self.attempts += 1
        if self.always_fail or self.attempts <= self.fail_times:
            raise ChannelSendError("invio SMS simulato fallito")
        message_id = f"FAKE{len(self.sent) + 1:06d}"
        self.sent.append(
            SentSms(to=to, body=body, sent_at=datetime.now(UTC), message_id=message_id)
        )
        return message_id


class TwilioSmsProvider:
    """Invio tramite l'API REST di Twilio con una semplice POST httpx."""

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        client: httpx.AsyncClient | None = None,
        api_base: str = TWILIO_API_BASE,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from = from_number
        self._client = client
        self._api_base = api_base
        self._timeout_s = timeout_s

    async def send(self, to: str, body: str) -> str:
        """Invia l'SMS; ogni errore diventa :class:`ChannelSendError` senza dati personali."""
        url = f"{self._api_base}/Accounts/{self._account_sid}/Messages.json"
        data = {"To": to, "From": self._from, "Body": body}
        auth = (self._account_sid, self._auth_token)
        try:
            if self._client is not None:
                response = await self._client.post(url, data=data, auth=auth)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    response = await client.post(url, data=data, auth=auth)
        except httpx.HTTPError as exc:
            raise ChannelSendError(
                f"errore di rete verso il fornitore SMS: {type(exc).__name__}"
            ) from None
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise ChannelSendError(f"il fornitore SMS ha risposto {response.status_code}")
        sid = response.json().get("sid")
        return str(sid) if sid else ""


def twilio_signature(auth_token: str, url: str, params: Mapping[str, str]) -> str:
    """Calcola ``X-Twilio-Signature``: HMAC-SHA1 di URL + parametri ordinati, in base64."""
    payload = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def validate_twilio_signature(
    auth_token: str, url: str, params: Mapping[str, str], signature: str | None
) -> bool:
    """Confronta in tempo costante la firma ricevuta con quella attesa."""
    if not signature or not auth_token:
        return False
    expected = twilio_signature(auth_token, url, params)
    return hmac.compare_digest(expected, signature)


def parse_sms_reply(text: str) -> SmsReply:
    """Riduce la risposta del cittadino a 1, 2, 3, STOP, AIUTO o ``other``."""
    cleaned = "".join(text.split()).strip(".!").upper()
    kind: ReplyKind = _REPLY_KEYWORDS.get(cleaned, "other")
    return SmsReply(kind=kind)
