"""Fixture condivise da tutti i test del workspace."""

import os

import pytest


@pytest.fixture
def database_url_test() -> str:
    """URL del database di test. Se manca, i test marcati ``db`` vengono saltati."""
    url = os.environ.get("DATABASE_URL_TEST")
    if not url:
        pytest.skip("DATABASE_URL_TEST non impostata: test del database saltato.")
    return url
