"""Gestione delle risposte SMS: 1/2/3, STOP, AIUTO, altro (storie B6, B9).

Il testo ricevuto vive solo in memoria per il tempo di ``parse_sms_reply``:
non si salva e non si scrive nei log.
"""

import logging
from collections import OrderedDict
from dataclasses import dataclass

from gateway.dispatcher import Cipher, Renderer
from gateway.personal_links import LinkBuilder
from gateway.store import NotifierStore
from onevisit_channels import ChannelSendError, SmsProvider, normalize_phone, parse_sms_reply

logger = logging.getLogger(__name__)

# Risposta 1/2/3 -> esito registrato come i pulsanti del web.
OUTCOME_FOR_REPLY = {"1": "ok", "2": "missing", "3": "other"}


class RecentIds:
    """Insieme limitato degli ultimi ``MessageSid`` visti (idempotenza del webhook)."""

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._ids: OrderedDict[str, None] = OrderedDict()

    def seen(self, message_id: str) -> bool:
        """Vero se l'id era gia' noto; altrimenti lo registra."""
        if message_id in self._ids:
            return True
        self._ids[message_id] = None
        if len(self._ids) > self._capacity:
            self._ids.popitem(last=False)
        return False


@dataclass(frozen=True)
class InboundContext:
    """Dipendenze della gestione delle risposte SMS."""

    sms: SmsProvider
    renderer: Renderer
    links: LinkBuilder
    cipher: Cipher
    assistant_base_url: str


async def _reply(ctx: InboundContext, to: str, kind: str, language: str, link: str) -> None:
    message = ctx.renderer(kind, language=language, channel="sms", days_left=None, link=link)
    try:
        await ctx.sms.send(to, message.text)
    except ChannelSendError as exc:
        logger.warning("risposta SMS %s non inviata (%s)", kind, exc)


async def handle_sms(store: NotifierStore, *, sender: str, text: str, ctx: InboundContext) -> str:
    """Elabora un SMS in arrivo e restituisce il tipo di risposta (solo per i log e i test)."""
    reply = parse_sms_reply(text)
    try:
        phone = normalize_phone(sender)
    except ValueError:
        return "invalid_sender"
    digest = ctx.cipher.digest(phone)
    found = store.find_by_phone_digest(digest)
    if found is None:
        logger.info("SMS da numero non registrato: nessuna risposta")
        return "unknown_contact"
    target, case_id = found
    language = target.language
    base = ctx.assistant_base_url
    if reply.kind == "STOP":
        # STOP vale per il numero, non per un solo contatto: tutti i casi smettono di scrivere.
        store.revoke_consents_by_phone(digest)
        store.commit()
        link = ctx.links.consents(case_id, target.contact_id) if case_id else base
        await _reply(ctx, phone, "revocation_confirm", language, link)
        return "revoked"
    if reply.kind == "AIUTO":
        link = ctx.links.consents(case_id, target.contact_id) if case_id else base
        await _reply(ctx, phone, "help", language, link)
        return "help"
    if reply.kind in OUTCOME_FOR_REPLY and case_id is not None:
        store.record_outcome(case_id, outcome=OUTCOME_FOR_REPLY[reply.kind])
        store.commit()
        await _reply(
            ctx, phone, "outcome_thanks", language, ctx.links.outcome(case_id, target.contact_id)
        )
        return "outcome"
    link = ctx.links.checklist(case_id, target.contact_id) if case_id else base
    await _reply(ctx, phone, "unrecognized", language, link)
    return "unrecognized"
