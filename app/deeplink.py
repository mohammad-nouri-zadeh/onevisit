"""Deep links from channels the City already has.

    https://onevisit.streamlit.app/?servizio=carta-identita&sede=ds549-11&data=2026-10-20&lang=it

in the booking confirmation email opens the app with the service, the office and the date
already set. The same link without office and date, with `canale=yesmilano` (the YesMilano
student guide) or `canale=benvenuto` (the City's welcome email to new residents), opens the
service only. The link carries no personal data: only a service id, an office id from open
dataset ds549, a date, a language and the channel. Unknown values are dropped, never guessed.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from urllib.parse import urlencode

from onevisit import kb

LANGS = ("it", "en", "ar", "zh", "es")
# Where the link was placed: booking confirmation email, welcome email, YesMilano student guide.
CHANNELS = ("prenotazione", "benvenuto", "yesmilano")
PUBLIC_URL = "https://onevisit.streamlit.app/"
_ID = re.compile(r"^[a-z0-9][a-z0-9\-]{0,60}$")


def _first(params: Mapping, key: str) -> str:
    value = params.get(key)
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()


def parse(params: Mapping) -> dict | None:
    """Service, office, date, language and channel from the query string; None without a known service."""
    service_id = _first(params, "servizio") or _first(params, "service")
    if not _ID.match(service_id) or not kb.get_service(service_id):
        return None
    office_id = _first(params, "sede") or _first(params, "office")
    offices = {o["id"]: o for o in kb.find_offices(limit=1000)}
    office = offices.get(office_id) if _ID.match(office_id or "-") else None
    date = None
    raw_date = _first(params, "data") or _first(params, "date")
    if raw_date:
        try:
            date = dt.date.fromisoformat(raw_date).isoformat()
        except ValueError:
            date = None
    lang = _first(params, "lang")
    channel = _first(params, "canale") or _first(params, "channel")
    if channel not in CHANNELS:
        channel = "prenotazione" if date or office else None
    return {
        "service_id": service_id,
        "office_id": office["id"] if office else None,
        "office_address": office["address"] if office else None,
        "date": date,
        "lang": lang if lang in LANGS else None,
        "channel": channel,
    }


def build(
    service_id: str,
    office_id: str | None = None,
    date: str | dt.date | None = None,
    lang: str | None = None,
    base: str = PUBLIC_URL,
    demo: bool = False,
    channel: str | None = None,
) -> str:
    """The link the City would add to its booking confirmation email (or welcome email, YesMilano guide)."""
    params = {"servizio": service_id}
    if office_id:
        params["sede"] = office_id
    if date:
        params["data"] = date.isoformat() if isinstance(date, dt.date) else str(date)
    if lang:
        params["lang"] = lang
    if channel in CHANNELS and channel != "prenotazione":
        params["canale"] = channel
    if demo:
        params["demo"] = "1"
    return f"{base}?{urlencode(params)}"
