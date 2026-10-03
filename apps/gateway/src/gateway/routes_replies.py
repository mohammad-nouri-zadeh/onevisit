"""Link di risposta delle email ``GET /r/{token}?choice=1|2|3`` (storie C7, B8).

Il token e' firmato e scade; la scelta viene registrata come il pulsante del web.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gateway.inbound import OUTCOME_FOR_REPLY
from gateway.web import TEMPLATES, get_deps, page_language
from onevisit_channels import PURPOSE_REPLY, LinkError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["replies"])

SECONDS_PER_DAY = 86_400


@router.get("/r/{token}", response_class=HTMLResponse)
def reply_link(request: Request, token: str, choice: str = "") -> HTMLResponse:
    """Registra l'esito scelto nell'email e mostra una pagina di ringraziamento."""
    deps = get_deps(request)
    lang = page_language(request)
    # Link "torna alla chat": la pagina iniziale dell'assistente web.
    chat_url = deps.settings.assistant_base_url
    max_age = deps.settings.link_max_age_days * SECONDS_PER_DAY
    try:
        payload = deps.signer.verify(token, PURPOSE_REPLY, max_age_s=max_age)
    except LinkError:
        logger.warning("link di risposta rifiutato: token non valido o scaduto")
        return TEMPLATES.TemplateResponse(
            request,
            "thanks.html",
            {"lang": lang, "ok": False, "details_url": None, "chat_url": chat_url},
            status_code=400,
        )
    outcome = OUTCOME_FOR_REPLY.get(choice)
    if outcome is None:
        return TEMPLATES.TemplateResponse(
            request,
            "thanks.html",
            {"lang": lang, "ok": False, "details_url": None, "chat_url": chat_url},
            status_code=400,
        )
    case_id = UUID(str(payload["case_id"]))
    contact = payload.get("contact_id")
    if deps.store_factory is not None:
        with deps.store_factory() as store:
            store.record_outcome(case_id, outcome=outcome)
            store.commit()
    else:
        logger.warning("link di risposta: database non configurato, esito non registrato")
    details = deps.links.outcome(case_id, UUID(contact)) if contact else None
    logger.info("esito registrato da link email per il caso %s", case_id)
    return TEMPLATES.TemplateResponse(
        request,
        "thanks.html",
        {"lang": lang, "ok": True, "details_url": details, "chat_url": chat_url},
    )
