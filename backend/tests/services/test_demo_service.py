from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from app.events.types import EventType
from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.shipment import Shipment
from app.models.support_ticket import SupportTicket, TicketPriority
from app.services import demo_service
from app.services.demo_service import ShipmentScenario, create_delayed_order


def _seed(db_session) -> Customer:
    customer = Customer(name="Demo", email=f"demo-{uuid4().hex[:8]}@example.com")
    db_session.add_all([customer, Product(name="Widget", price=Decimal("10.00"))])
    db_session.commit()
    return customer


@pytest.fixture
def published():
    events = []
    with (
        patch.object(
            demo_service,
            "publish_event",
            side_effect=lambda e: events.append(e) or "1-0",
        ),
        patch.object(demo_service, "redis_client") as fake_redis,
    ):
        yield events, fake_redis


def test_creates_delayed_order_with_shipment_and_publishes_event(db_session, published):
    events, fake_redis = published
    customer = _seed(db_session)

    result = create_delayed_order(
        db_session, delay_days=9, shipment_scenario=ShipmentScenario.LOST
    )

    order = db_session.get(Order, result["order_id"])
    assert order.customer_id == customer.id
    assert order.status == OrderStatus.SHIPPED
    assert order.total_amount > 0
    assert len(order.items) == 1

    shipment = db_session.query(Shipment).filter_by(order_id=order.id).one()
    assert shipment.status == "LOST"

    assert len(events) == 1
    event = events[0]
    assert event.event_type == EventType.ORDER_DELAYED
    assert event.event_id == result["event_id"]
    assert event.data["order_id"] == order.id
    assert event.data["delay_days"] == 9
    assert result["message_id"] == "1-0"

    # Marked as published today, so the order monitor won't re-send it.
    dedupe_key = fake_redis.set.call_args.args[0]
    assert dedupe_key.startswith(f"delayed_order:{order.id}:")


def test_none_scenario_creates_no_shipment(db_session, published):
    _seed(db_session)

    result = create_delayed_order(
        db_session, delay_days=3, shipment_scenario=ShipmentScenario.NONE
    )

    order = db_session.get(Order, result["order_id"])
    assert order.status == OrderStatus.PROCESSING
    assert db_session.query(Shipment).filter_by(order_id=order.id).count() == 0


def test_unknown_customer_raises(db_session, published):
    _seed(db_session)

    with pytest.raises(ValueError, match="Customer 999 not found"):
        create_delayed_order(
            db_session,
            delay_days=3,
            shipment_scenario=ShipmentScenario.IN_TRANSIT,
            customer_id=999,
        )
    assert published[0] == []


def test_empty_database_raises_instead_of_publishing(db_session, published):
    with pytest.raises(ValueError, match="make seed"):
        create_delayed_order(
            db_session, delay_days=3, shipment_scenario=ShipmentScenario.IN_TRANSIT
        )
    assert published[0] == []


def _make_order(db_session, customer) -> Order:
    order = Order(customer_id=customer.id, total_amount=10, status=OrderStatus.SHIPPED)
    db_session.add(order)
    db_session.commit()
    return order


def test_customer_ticket_is_filed_as_the_orders_customer(db_session, published):
    events, _ = published
    customer = _seed(db_session)
    order = _make_order(db_session, customer)

    result = demo_service.create_customer_ticket(
        db_session,
        subject="Wrong item",
        message="I got a blue one, ordered red.",
        priority=TicketPriority.LOW,
        order_id=order.id,
    )

    ticket = db_session.get(SupportTicket, result["ticket_id"])
    assert ticket.customer_id == customer.id
    assert ticket.order_id == order.id
    assert ticket.priority == "LOW"
    assert ticket.status == "OPEN"

    assert len(events) == 1
    assert events[0].event_type == EventType.TICKET_CREATED
    assert events[0].event_id == result["event_id"]
    assert events[0].data["ticket_id"] == ticket.id


def test_customer_ticket_picks_a_random_order_when_none_given(db_session, published):
    customer = _seed(db_session)
    order = _make_order(db_session, customer)

    result = demo_service.create_customer_ticket(db_session, subject="s", message="m")

    assert result["order_id"] == order.id


def test_customer_ticket_unknown_order_raises(db_session, published):
    with pytest.raises(ValueError, match="Order 42 not found"):
        demo_service.create_customer_ticket(
            db_session, subject="s", message="m", order_id=42
        )
    assert published[0] == []


def test_customer_email_creates_new_customer_for_the_order(db_session, published):
    _seed(db_session)

    result = create_delayed_order(
        db_session,
        delay_days=5,
        shipment_scenario=ShipmentScenario.LOST,
        customer_email="jane.doe@example.com",
    )

    customer = db_session.get(Customer, result["customer_id"])
    assert customer.email == "jane.doe@example.com"
    assert customer.name == "Jane Doe"
    assert db_session.get(Order, result["order_id"]).customer_id == customer.id


def test_customer_email_reuses_existing_customer_case_insensitively(
    db_session, published
):
    _seed(db_session)
    existing = Customer(name="Jane", email="Jane@Example.com")
    db_session.add(existing)
    db_session.commit()
    before = db_session.query(Customer).count()

    result = create_delayed_order(
        db_session,
        delay_days=5,
        shipment_scenario=ShipmentScenario.IN_TRANSIT,
        customer_email="jane@example.com",
    )

    assert result["customer_id"] == existing.id
    assert db_session.query(Customer).count() == before


def test_customer_id_and_email_together_raise(db_session, published):
    customer = _seed(db_session)

    with pytest.raises(ValueError, match="not both"):
        create_delayed_order(
            db_session,
            delay_days=5,
            shipment_scenario=ShipmentScenario.LOST,
            customer_id=customer.id,
            customer_email="x@example.com",
        )


def test_complaint_by_email_uses_customers_latest_order(db_session, published):
    customer = _seed(db_session)
    _make_order(db_session, customer)
    latest = _make_order(db_session, customer)
    other = Customer(name="Other", email="other@example.com")
    db_session.add(other)
    db_session.commit()
    _make_order(db_session, other)

    result = demo_service.create_customer_ticket(
        db_session, subject="s", message="m", customer_email=customer.email.upper()
    )

    assert result["order_id"] == latest.id
    assert result["customer_id"] == customer.id


def test_complaint_order_must_belong_to_email(db_session, published):
    customer = _seed(db_session)
    other = Customer(name="Other", email="other@example.com")
    db_session.add(other)
    db_session.commit()
    others_order = _make_order(db_session, other)

    with pytest.raises(ValueError, match="doesn't belong"):
        demo_service.create_customer_ticket(
            db_session,
            subject="s",
            message="m",
            order_id=others_order.id,
            customer_email=customer.email,
        )
    assert published[0] == []


def test_complaint_unknown_email_raises(db_session, published):
    _seed(db_session)

    with pytest.raises(ValueError, match="simulate a delayed order"):
        demo_service.create_customer_ticket(
            db_session, subject="s", message="m", customer_email="nobody@example.com"
        )


def test_customer_ticket_is_acknowledged_with_status_link(db_session, published):
    from app.models.notification import Notification

    customer = _seed(db_session)
    order = _make_order(db_session, customer)

    result = demo_service.create_customer_ticket(
        db_session, subject="Wrong colour", message="m", order_id=order.id
    )

    notification = db_session.query(Notification).filter_by(order_id=order.id).one()
    assert notification.recipient == customer.email
    assert f"#{result['ticket_id']}" in notification.subject
    assert "Wrong colour" in notification.content
    assert f"?order={order.id}" in notification.content
