"""Webhook ``POST /sms/inbound`` in stile Twilio (storie C6, B6, B9).

Se il fornitore e' Twilio la firma ``X-Twilio-Signature`` e' obbligatoria; il fornitore
finto (sviluppo e demo) accetta richieste senza firma. Le richieste rifiutate vengono
registrate senza contenuto.
"""

import logging

from fastapi import APIRouter, Request, Response

from gateway.deps import GatewayDeps
from gateway.inbound import InboundContext, handle_sms
from gateway.web import get_deps
from onevisit_channels import ChannelError, SmsAdapter, validate_twilio_signature

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sms"])

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _signed_url(request: Request, deps: GatewayDeps) -> str:
    """URL pubblica firmata da Twilio (quella del gateway, non quella interna)."""
    base = deps.settings.gateway_base_url.rstrip("/")
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{base}{request.url.path}{query}"


def inbound_context(deps: GatewayDeps) -> InboundContext | None:
    """Contesto per :func:`handle_sms`, se cifratura e database sono configurati."""
    if deps.cipher is None:
        return None
    return InboundContext(
        sms=deps.sms,
        renderer=deps.renderer,
        links=deps.links,
        cipher=deps.cipher,
        assistant_base_url=deps.settings.assistant_base_url,
    )


async def process_inbound(deps: GatewayDeps, params: dict[str, str]) -> str:
    """Elabora i campi del webhook gia' verificati; usato anche dalla pagina demo."""
    try:
        inbound = SmsAdapter(deps.sms).parse_inbound(params)
    except ChannelError:
        return "invalid"
    if inbound.provider_message_id and deps.recent_ids.seen(inbound.provider_message_id):
        return "duplicate"
    ctx = inbound_context(deps)
    if ctx is None or deps.store_factory is None:
        logger.warning("SMS in arrivo ignorato: database o cifratura non configurati")
        return "not_configured"
    with deps.store_factory() as store:
        result = await handle_sms(store, sender=inbound.sender, text=inbound.text, ctx=ctx)
    logger.info("SMS in arrivo gestito: %s", result)
    return result


@router.post("/sms/inbound")
async def sms_inbound(request: Request) -> Response:
    """Riceve un SMS dal fornitore e risponde con TwiML vuoto (le risposte partono via API)."""
    deps = get_deps(request)
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}
    if deps.settings.uses_twilio:
        signature = request.headers.get("X-Twilio-Signature")
        url = _signed_url(request, deps)
        if not validate_twilio_signature(deps.settings.twilio_auth_token, url, params, signature):
            logger.warning("webhook SMS rifiutato: firma non valida")
            return Response(status_code=403)
    result = await process_inbound(deps, params)
    if result == "invalid":
        logger.warning("webhook SMS rifiutato: richiesta incompleta")
        return Response(status_code=400)
    return Response(content=EMPTY_TWIML, media_type="application/xml")
