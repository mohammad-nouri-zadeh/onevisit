"""Fixture condivise da tutti i test del workspace."""

import os
from collections.abc import Iterator

import pytest


@pytest.fixture
def database_url_test() -> str:
    """URL del database di test. Se manca, i test marcati ``db`` vengono saltati."""
    url = os.environ.get("DATABASE_URL_TEST")
    if not url:
        pytest.skip("DATABASE_URL_TEST non impostata: test del database saltato.")
    return url


@pytest.fixture(scope="module")
def migrated_db_url() -> Iterator[str]:
    """Database di test con nome univoco e migrazioni applicate (storia C2).

    Si crea una volta per modulo di test e si elimina alla fine del modulo: così i
    pacchetti non si vedono le righe a vicenda (per esempio notifiche in scadenza
    create da un'altra app con un'altra cifratura). Salta se manca
    ``DATABASE_URL_TEST`` (URL amministrativa usata per creare il database).
    """
    admin_url = os.environ.get("DATABASE_URL_TEST")
    if not admin_url:
        pytest.skip("DATABASE_URL_TEST non impostata: test del database saltato.")
    from onevisit_db.testing import migrated_database

    with migrated_database(admin_url) as url:
        yield url
