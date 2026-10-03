"""Accesso dimostrativo per ruolo con cookie firmato (storia C12).

Solo per l'hackathon: si sceglie un ruolo (redazione, ufficio, direzione) senza
password. In produzione l'accesso passera' dal sistema del Comune via OIDC (Authlib),
non implementato oggi. Il cookie contiene solo il ruolo, mai un nome.
"""

from typing import Literal

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer

Role = Literal["redazione", "ufficio", "direzione"]
ROLES: tuple[Role, ...] = ("redazione", "ufficio", "direzione")
COOKIE_NAME = "ov_dashboard_role"
_SALT = "dashboard-role"


class RoleSigner:
    """Firma e verifica il ruolo nel cookie."""

    def __init__(self, secret: str, *, max_age_s: int) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_SALT)
        self._max_age_s = max_age_s

    def sign(self, role: Role) -> str:
        """Valore del cookie per il ruolo."""
        return self._serializer.dumps(role)

    def verify(self, token: str | None) -> Role | None:
        """Ruolo dal cookie, oppure ``None`` se assente, scaduto o manomesso."""
        if not token:
            return None
        try:
            value = self._serializer.loads(token, max_age=self._max_age_s)
        except BadSignature:
            return None
        return next((r for r in ROLES if r == value), None)


def current_role(request: Request) -> Role:
    """Dipendenza FastAPI: il ruolo dimostrativo, o reindirizza alla pagina di accesso."""
    signer: RoleSigner = request.app.state.role_signer
    role = signer.verify(request.cookies.get(COOKIE_NAME))
    if role is None:
        raise HTTPException(status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return role


def require(role: Role, allowed: tuple[Role, ...]) -> None:
    """Solleva 403 se il ruolo non e' tra quelli ammessi."""
    if role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="ruolo non autorizzato")
