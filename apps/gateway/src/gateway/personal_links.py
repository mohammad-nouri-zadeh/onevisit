"""Costruzione dei link personali inseriti nei messaggi (storie B7, B9, C7)."""

from dataclasses import dataclass
from uuid import UUID

from onevisit_channels import (
    PURPOSE_CHECKLIST,
    PURPOSE_CONSENTS,
    PURPOSE_EMAIL_CONFIRM,
    PURPOSE_OUTCOME,
    PURPOSE_REPLY,
    LinkSigner,
)


@dataclass(frozen=True)
class LinkBuilder:
    """Firma i token e compone le URL di assistant_web e del gateway."""

    signer: LinkSigner
    assistant_base_url: str
    gateway_base_url: str

    def _url(self, base: str, prefix: str, purpose: str, case_id: UUID, contact_id: UUID) -> str:
        token = self.signer.sign(purpose, case_id, contact_id)
        return f"{base.rstrip('/')}/{prefix}/{token}"

    def checklist(self, case_id: UUID, contact_id: UUID) -> str:
        """Checklist personale su assistant_web (``/c/{token}``)."""
        return self._url(self.assistant_base_url, "c", PURPOSE_CHECKLIST, case_id, contact_id)

    def outcome(self, case_id: UUID, contact_id: UUID) -> str:
        """Pagina dell'esito su assistant_web (``/o/{token}``)."""
        return self._url(self.assistant_base_url, "o", PURPOSE_OUTCOME, case_id, contact_id)

    def consents(self, case_id: UUID, contact_id: UUID) -> str:
        """Gestione dei consensi su assistant_web (``/consents/{token}``)."""
        return self._url(self.assistant_base_url, "consents", PURPOSE_CONSENTS, case_id, contact_id)

    def email_confirm(self, case_id: UUID, contact_id: UUID) -> str:
        """Conferma dell'indirizzo email su assistant_web (``/confirm/{token}``).

        La conferma programma promemoria e follow-up: deve arrivare alla rotta di
        assistant_web che lo fa, non alla pagina dei consensi.
        """
        return self._url(
            self.assistant_base_url, "confirm", PURPOSE_EMAIL_CONFIRM, case_id, contact_id
        )

    def reply(self, case_id: UUID, contact_id: UUID) -> str:
        """Base dei link di risposta delle email (``/r/{token}``, poi ``?choice=1|2|3``)."""
        return self._url(self.gateway_base_url, "r", PURPOSE_REPLY, case_id, contact_id)

    def for_kind(self, kind: str, channel: str, case_id: UUID, contact_id: UUID) -> str:
        """Link principale del messaggio di ``kind`` sul canale indicato."""
        if kind in ("followup", "followup_nudge"):
            if channel == "email":
                return self.reply(case_id, contact_id)
            return self.outcome(case_id, contact_id)
        if kind == "revocation_confirm":
            return self.consents(case_id, contact_id)
        if kind == "email_confirm":
            return self.email_confirm(case_id, contact_id)
        return self.checklist(case_id, contact_id)
