"""Pagina ``/demo/phone``: un telefono finto con gli SMS catturati (demo e video).

Attiva solo in modalita' demo o in sviluppo, e solo con il fornitore SMS finto.
I numeri sono mascherati; i messaggi in arrivo non vengono mostrati ne' conservati.
"""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gateway.routes_sms import process_inbound
from gateway.web import TEMPLATES, get_deps, page_language

router = APIRouter(tags=["demo"])

# Cifre finali del numero mostrate nella pagina demo.
VISIBLE_DIGITS = 2
# Aggiornamento automatico della pagina demo, in secondi.
REFRESH_S = 3
DEMO_REPLIES = ("1", "2", "3", "AIUTO", "STOP")


def _mask(number: str) -> str:
    return "•" * max(len(number) - VISIBLE_DIGITS, 0) + number[-VISIBLE_DIGITS:]


@router.get("/demo/phone", response_class=HTMLResponse)
def demo_phone(request: Request) -> HTMLResponse:
    """Mostra gli SMS inviati dal fornitore finto, dal piu' recente."""
    deps = get_deps(request)
    if not deps.settings.demo_pages_enabled or deps.fake_sms is None:
        raise HTTPException(status_code=404)
    messages = [
        {"to": _mask(sms.to), "body": sms.body, "at": sms.sent_at.strftime("%H:%M:%S")}
        for sms in reversed(deps.fake_sms.sent)
    ]
    return TEMPLATES.TemplateResponse(
        request,
        "phone.html",
        {
            "lang": page_language(request),
            "messages": messages,
            "replies": DEMO_REPLIES,
            "refresh_s": REFRESH_S,
        },
    )


@router.post("/demo/phone/reply")
async def demo_reply(request: Request, body: str = Form(...)) -> RedirectResponse:
    """Simula la risposta del telefono all'ultimo SMS ricevuto (solo parole chiave)."""
    deps = get_deps(request)
    if not deps.settings.demo_pages_enabled or deps.fake_sms is None or not deps.fake_sms.sent:
        raise HTTPException(status_code=404)
    if body not in DEMO_REPLIES:
        raise HTTPException(status_code=400)
    sender = deps.fake_sms.sent[-1].to
    await process_inbound(deps, {"From": sender, "Body": body})
    return RedirectResponse("/demo/phone", status_code=303)
