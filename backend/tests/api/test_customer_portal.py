from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.api.customer_portal import lookup_order
from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.shipment import Shipment, ShipmentStatus
from fastapi import HTTPException


def _make_customer(db_session, email: str | None = None) -> Customer:
    unique = uuid4().hex[:8]
    customer = Customer(
        name="Test Customer", email=email or f"test-{unique}@example.com"
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


def _make_order(db_session, customer_id: int, **overrides) -> Order:
    order = Order(
        customer_id=customer_id,
        total_amount=42,
        expected_delivery=overrides.pop("expected_delivery", None),
        status=overrides.pop("status", OrderStatus.PENDING),
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def test_lookup_order_with_matching_email_returns_order(db_session):
    customer = _make_customer(db_session, email="jane@example.com")
    order = _make_order(db_session, customer.id)

    result = lookup_order(order.id, email="jane@example.com", db=db_session)

    assert result.order_id == order.id
    assert result.customer_id == customer.id


def test_lookup_order_email_match_is_case_insensitive(db_session):
    customer = _make_customer(db_session, email="Jane@Example.com")
    order = _make_order(db_session, customer.id)

    result = lookup_order(order.id, email="jane@example.com", db=db_session)

    assert result.order_id == order.id


def test_lookup_order_with_wrong_email_raises_generic_404(db_session):
    customer = _make_customer(db_session, email="jane@example.com")
    order = _make_order(db_session, customer.id)

    with pytest.raises(HTTPException) as exc_info:
        lookup_order(order.id, email="wrong@example.com", db=db_session)

    assert exc_info.value.status_code == 404


def test_lookup_nonexistent_order_raises_same_generic_404(db_session):
    customer = _make_customer(db_session, email="jane@example.com")
    order = _make_order(db_session, customer.id)

    with pytest.raises(HTTPException) as wrong_email_exc:
        lookup_order(order.id, email="wrong@example.com", db=db_session)

    with pytest.raises(HTTPException) as missing_order_exc:
        lookup_order(order.id + 999, email="jane@example.com", db=db_session)

    assert wrong_email_exc.value.status_code == missing_order_exc.value.status_code
    assert wrong_email_exc.value.detail == missing_order_exc.value.detail


def test_lookup_order_reports_delay_for_overdue_undelivered_order(db_session):
    customer = _make_customer(db_session, email="jane@example.com")
    today = datetime.now(UTC).date()
    order = _make_order(
        db_session,
        customer.id,
        expected_delivery=today - timedelta(days=3),
        status=OrderStatus.SHIPPED,
    )

    result = lookup_order(order.id, email="jane@example.com", db=db_session)

    assert result.is_delayed is True
    assert result.delay_days == 3


def test_lookup_order_not_delayed_when_delivered(db_session):
    customer = _make_customer(db_session, email="jane@example.com")
    today = datetime.now(UTC).date()
    order = _make_order(
        db_session,
        customer.id,
        expected_delivery=today - timedelta(days=3),
        status=OrderStatus.DELIVERED,
    )

    result = lookup_order(order.id, email="jane@example.com", db=db_session)

    assert result.is_delayed is False
    assert result.delay_days is None


def test_lookup_order_includes_shipment_info(db_session):
    customer = _make_customer(db_session, email="jane@example.com")
    order = _make_order(db_session, customer.id)

    shipment = Shipment(
        order_id=order.id,
        carrier="UPS",
        tracking_number="1Z999",
        status=ShipmentStatus.IN_TRANSIT,
        last_location="Denver, CO",
        last_updated=datetime.now(UTC),
    )
    db_session.add(shipment)
    db_session.commit()

    result = lookup_order(order.id, email="jane@example.com", db=db_session)

    assert result.shipment is not None
    assert result.shipment.tracking_number == "1Z999"
