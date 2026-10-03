"""Utilità condivise dalle rotte: template, cookie di sessione, contesto comune (B1)."""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

from assistant_web.i18n import messages
from assistant_web.runtime import Runtime

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
COOKIE_NAME = "ov_session"
_COOKIE_SALT = "onevisit.session"


def runtime(request: Request) -> Runtime:
    """Il contenitore delle dipendenze dell'app."""
    rt: Runtime = request.app.state.runtime
    return rt


def _serializer(rt: Runtime) -> URLSafeSerializer:
    return URLSafeSerializer(rt.session_secret, salt=_COOKIE_SALT)


def session_id_from_cookie(request: Request) -> str | None:
    """Id opaco dal cookie firmato; ``None`` se manca o la firma non vale."""
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        value = _serializer(runtime(request)).loads(raw)
    except BadSignature:
        return None
    return value if isinstance(value, str) else None


def signed_session_cookie(request: Request, session_id: str) -> str:
    """Valore firmato del cookie per l'id di sessione."""
    return str(_serializer(runtime(request)).dumps(session_id))


def context(language: str, **extra: Any) -> dict[str, Any]:
    """Contesto comune dei template: lingua e testi."""
    return {"lang": language, "t": messages(language), **extra}
