from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
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


class FakeRedis:
    """Dict-backed stand-in with real SET NX semantics."""

    def __init__(self):
        self.store = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)


def _fake_redis():
    return FakeRedis()


def test_detect_delayed_orders_without_limit_publishes_all(db_session):
    customer = _make_customer(db_session)
    for _ in range(3):
        _make_delayed_order(db_session, customer.id)

    with (
        patch.object(order_monitor, "redis_client", _fake_redis()),
        patch.object(order_monitor, "publish_event") as mock_publish,
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
    ):
        published = order_monitor.detect_delayed_orders(db_session, limit=2)

    assert published == 2
    assert mock_publish.call_count == 2


def test_publishes_without_sleeping_inside_the_request(db_session):
    """Regression: it slept 5 s per order inside the HTTP request — with no
    limit and thousands of overdue orders, a single call ran for hours."""
    customer = _make_customer(db_session)
    for _ in range(3):
        _make_delayed_order(db_session, customer.id)

    with (
        patch.object(order_monitor, "redis_client", _fake_redis()),
        patch.object(order_monitor, "publish_event"),
        patch("time.sleep") as mock_sleep,
    ):
        order_monitor.detect_delayed_orders(db_session)

    mock_sleep.assert_not_called()


def test_order_already_published_today_is_skipped(db_session):
    customer = _make_customer(db_session)
    order = _make_delayed_order(db_session, customer.id)
    redis = _fake_redis()
    redis.set(
        order_monitor.delayed_order_dedupe_key(order.id, datetime.now(UTC).date()),
        "1",
    )

    with (
        patch.object(order_monitor, "redis_client", redis),
        patch.object(order_monitor, "publish_event") as mock_publish,
    ):
        published = order_monitor.detect_delayed_orders(db_session)

    assert published == 0
    mock_publish.assert_not_called()


def test_publish_failure_gives_the_slot_back(db_session):
    customer = _make_customer(db_session)
    order = _make_delayed_order(db_session, customer.id)
    redis = _fake_redis()

    with (
        patch.object(order_monitor, "redis_client", redis),
        patch.object(
            order_monitor, "publish_event", side_effect=ConnectionError("down")
        ),
        pytest.raises(ConnectionError),
    ):
        order_monitor.detect_delayed_orders(db_session)

    key = order_monitor.delayed_order_dedupe_key(order.id, datetime.now(UTC).date())
    assert key not in redis.store
