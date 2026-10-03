"""Link personali del gateway allineati alle rotte di assistant_web (storie B5, B7, B9)."""

from uuid import uuid4

from gateway.personal_links import LinkBuilder
from onevisit_channels import PURPOSE_CHECKLIST, PURPOSE_EMAIL_CONFIRM, LinkSigner

from .conftest import LINK_KEY

# Durata di validita' usata solo per verificare i token nel test (un giorno).
MAX_AGE_S = 86_400


def test_email_confirm_link_goes_to_the_assistant_confirm_route(links: LinkBuilder) -> None:
    case_id, contact_id = uuid4(), uuid4()

    url = links.for_kind("email_confirm", "email", case_id, contact_id)

    prefix = "http://assistant.test/confirm/"
    assert url.startswith(prefix)
    data = LinkSigner(LINK_KEY).verify(url.removeprefix(prefix), PURPOSE_EMAIL_CONFIRM, MAX_AGE_S)
    assert data == {"case_id": str(case_id), "contact_id": str(contact_id)}


def test_reminder_link_goes_to_the_checklist(links: LinkBuilder) -> None:
    case_id, contact_id = uuid4(), uuid4()

    url = links.for_kind("reminder", "email", case_id, contact_id)

    prefix = "http://assistant.test/c/"
    assert url.startswith(prefix)
    data = LinkSigner(LINK_KEY).verify(url.removeprefix(prefix), PURPOSE_CHECKLIST, MAX_AGE_S)
    assert data["case_id"] == str(case_id)
