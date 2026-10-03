import pytest
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.base import Base
from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.shipment import Shipment
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client_and_session(monkeypatch):
    """Real HTTP round-trip, so FastAPI's response_model validation runs —
    calling the route function directly would skip it, which is exactly
    where the original bug lived."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def _db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    app.dependency_overrides[get_db] = _db
    try:
        yield TestClient(app, raise_server_exceptions=False), session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _make_order(session_factory) -> int:
    db = session_factory()
    customer = Customer(name="A", email="a@example.com")
    db.add(customer)
    db.commit()
    order = Order(customer_id=customer.id, total_amount=10)
    db.add(order)
    db.commit()
    order_id = order.id
    db.close()
    return order_id


def _post(client, order_id, tracking="TRK-1"):
    return client.post(
        f"/api/v1/shipments/{order_id}",
        params={"carrier": "UPS", "tracking_number": tracking},
        headers={"X-API-Key": "test-admin-key"},
    )


def test_create_shipment_returns_it_and_marks_order_shipped(client_and_session):
    """Regression: the response schema declared `last_update` while the model
    has `last_updated`, so every call committed the shipment and then 500'd —
    and it set the order status to "Shipped", which isn't an OrderStatus."""
    client, session_factory = client_and_session
    order_id = _make_order(session_factory)

    response = _post(client, order_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tracking_number"] == "TRK-1"
    assert body["last_updated"]
    db = session_factory()
    assert db.get(Order, order_id).status == OrderStatus.SHIPPED.value


def test_duplicate_tracking_number_is_a_400_not_a_500(client_and_session):
    client, session_factory = client_and_session
    first = _make_order(session_factory)
    db = session_factory()
    second_order = Order(customer_id=db.get(Order, first).customer_id, total_amount=5)
    db.add(second_order)
    db.commit()
    second = second_order.id
    db.close()

    assert _post(client, first, "DUP").status_code == 200
    response = _post(client, second, "DUP")

    assert response.status_code == 400
    assert session_factory().query(Shipment).count() == 1


def test_monitor_endpoint_rejects_unbounded_publish(client_and_session, monkeypatch):
    """POST /orders/monitor/delayed now has a bounded limit (default 10, max
    100) — every published order becomes a full agent run."""
    client, _ = client_and_session
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)

    response = client.post(
        "/api/v1/orders/monitor/delayed",
        params={"limit": 5000},
        headers={"X-API-Key": "test-admin-key"},
    )

    assert response.status_code == 422
