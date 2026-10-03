"""Link personali firmati per checklist, esito, consensi e risposte (storie B6, B9, C7).

Il token contiene solo identificativi opachi (``case_id`` e ``contact_id``), mai dati
personali. Ogni scopo ha il proprio sale, cosi' un token non vale per un altro scopo.
"""

from uuid import UUID

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from onevisit_channels.errors import LinkError

# Scopi dei link condivisi tra assistant_web e gateway.
PURPOSE_CHECKLIST = "checklist"  # /c/{token} su assistant_web
PURPOSE_OUTCOME = "outcome"  # /o/{token} su assistant_web
PURPOSE_CONSENTS = "consents"  # /consents/{token} su assistant_web
PURPOSE_REPLY = "reply"  # /r/{token}?choice=1|2|3 sul gateway
PURPOSE_EMAIL_CONFIRM = "email_confirm"  # conferma dell'indirizzo email

_SALT_PREFIX = "onevisit.link."
# Unico ambiente in cui si accetta la chiave di sviluppo condivisa.
DEVELOPMENT_ENVIRONMENT = "development"
# Chiave pubblica, valida SOLO in sviluppo: assistant_web e gateway la usano entrambe
# quando ONEVISIT_LINK_SIGNING_KEY e' vuota, cosi' i link firmati dall'una valgono
# nell'altra. Fuori sviluppo :func:`resolve_link_signing_key` rifiuta di partire.
DEV_LINK_SIGNING_KEY = "onevisit-development-only-link-key-not-secret"


def resolve_link_signing_key(configured: str, *, environment: str) -> str:
    """Chiave di firma da usare: quella configurata, oppure quella di sviluppo.

    Fuori dall'ambiente ``development`` una chiave vuota e' un errore (fail closed):
    con una chiave nota chiunque potrebbe creare link personali validi.
    """
    if configured:
        return configured
    if environment == DEVELOPMENT_ENVIRONMENT:
        return DEV_LINK_SIGNING_KEY
    raise LinkError("ONEVISIT_LINK_SIGNING_KEY obbligatoria fuori dallo sviluppo")


class LinkSigner:
    """Firma e verifica dei token (itsdangerous, sale diverso per ogni scopo)."""

    def __init__(self, secret: str) -> None:
        if not secret:
            raise LinkError("chiave di firma dei link mancante")
        self._secret = secret

    def _serializer(self, purpose: str) -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(self._secret, salt=_SALT_PREFIX + purpose)

    def sign(self, purpose: str, case_id: UUID | str, contact_id: UUID | str | None = None) -> str:
        """Crea il token per uno scopo."""
        payload = {
            "case_id": str(case_id),
            "contact_id": str(contact_id) if contact_id is not None else None,
        }
        return str(self._serializer(purpose).dumps(payload))

    def verify(self, token: str, purpose: str, max_age_s: int) -> dict[str, str | None]:
        """Verifica firma, scopo e scadenza; restituisce ``case_id`` e ``contact_id``."""
        try:
            data = self._serializer(purpose).loads(token, max_age=max_age_s)
        except SignatureExpired:
            raise LinkError("link scaduto") from None
        except BadSignature:
            raise LinkError("link non valido") from None
        if not isinstance(data, dict) or not isinstance(data.get("case_id"), str):
            raise LinkError("link non valido")
        contact = data.get("contact_id")
        return {
            "case_id": data["case_id"],
            "contact_id": contact if isinstance(contact, str) else None,
        }
