from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.services import order_monitor


def _make_customer(db_session) -> Customer:
    unique = uuid4().hex[:8]
    customer = Customer(name="Test Customer", email=f"test-{unique}@example.com")
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


def _make_delayed_order(db_session, customer_id: int) -> Order:
    order = Order(
        customer_id=customer_id,
        total_amount=42,
        expected_delivery=datetime.now(UTC).date() - timedelta(days=3),
        status=OrderStatus.SHIPPED,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def _fake_redis():
    """Minimal stand-in: exists() always False, set()/nothing recorded needed here."""

    class FakeRedis:
        def exists(self, key):
            return False

        def set(self, *args, **kwargs):
            pass

    return FakeRedis()


def test_detect_delayed_orders_without_limit_publishes_all(db_session):
    customer = _make_customer(db_session)
    for _ in range(3):
        _make_delayed_order(db_session, customer.id)

    with (
        patch.object(order_monitor, "redis_client", _fake_redis()),
        patch.object(order_monitor, "publish_event") as mock_publish,
        patch.object(order_monitor.time, "sleep"),
    ):
        published = order_monitor.detect_delayed_orders(db_session)

    assert published == 3
    assert mock_publish.call_count == 3


def test_detect_delayed_orders_with_limit_stops_early(db_session):
    customer = _make_customer(db_session)
    for _ in range(5):
        _make_delayed_order(db_session, customer.id)

    with (
        patch.object(order_monitor, "redis_client", _fake_redis()),
        patch.object(order_monitor, "publish_event") as mock_publish,
        patch.object(order_monitor.time, "sleep"),
    ):
        published = order_monitor.detect_delayed_orders(db_session, limit=2)

    assert published == 2
    assert mock_publish.call_count == 2
