"""Verifica dei permessi sul database reale (storia C2). Gira solo dentro Docker."""

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.db


def test_database_is_reachable(database_url_test: str) -> None:
    engine = create_engine(database_url_test)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
