"""Il servizio risponde al controllo di salute."""

from fastapi.testclient import TestClient

from dashboard.main import create_app


def test_health_returns_ok_and_service_name() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "dashboard"}
