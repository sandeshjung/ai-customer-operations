from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_list_tickets_returns_200(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    response = client.get("/api/v1/tickets", headers={"X-API-Key": "test-admin-key"})

    assert response.status_code == 200
    assert isinstance(response.json(), list)
