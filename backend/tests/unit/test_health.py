from app.main import app
from fastapi.testclient import TestClient


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.json() == {"status": "ok", "service": "DocMind API"}


def test_api_health_reports_model_gateway() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "model_gateway" in response.json()
