from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_list_tickets_returns_200():
    response = client.get("/api/v1/tickets")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
