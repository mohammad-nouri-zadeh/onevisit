"""Fixture del pannello: app con dati finti in memoria e accesso per ruolo."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.config import Settings
from dashboard.deps import get_panel_data
from dashboard.main import create_app
from dashboard.testing import FakePanelData

REPO_DATA = Path(__file__).resolve().parents[3] / "data"


@pytest.fixture
def fake_data() -> FakePanelData:
    return FakePanelData()


@pytest.fixture
def client_as(fake_data: FakePanelData) -> Callable[[str], TestClient]:
    def make(role: str) -> TestClient:
        app = create_app(Settings(session_secret="test-secret", data_dir=REPO_DATA))
        app.dependency_overrides[get_panel_data] = lambda: fake_data
        client = TestClient(app)
        client.post("/login", data={"role": role}, follow_redirects=False)
        return client

    return make
