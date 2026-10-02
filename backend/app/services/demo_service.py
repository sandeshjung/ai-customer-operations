"""Demo simulator for the admin console (timelines in order_timeline.py):

- create_delayed_order: one delayed order in a chosen scenario, with
  ORDER_DELAYED published straight away — exercises the whole pipeline.
- create_customer_ticket: a customer-written complaint, with TICKET_CREATED
  published straight away — exercises the triage agent on its own, on text a
  customer (not the delayed-order agent) wrote.
"""

import random
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from app.core.logging import get_logger
from app.core.redis import redis_client
from app.events.publisher import publish_event
from app.events.schemas import Event
from app.events.types import EventType
from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.shipment import Shipment, ShipmentStatus
from app.models.support_ticket import SupportTicket, TicketPriority, TicketStatus
from app.services.customer_emails import (
    customer_first_name,
    send_customer_email,
    ticket_acknowledgement,
)
from app.services.order_monitor import delayed_order_dedupe_key
from sqlalchemy import func
from sqlalchemy.orm import Session

logger = get_logger(__name__)

DEMO_CARRIERS = ["UPS", "FedEx", "DHL", "USPS"]


class ShipmentScenario(StrEnum):
    IN_TRANSIT = "IN_TRANSIT"
    EXCEPTION = "EXCEPTION"
    LOST = "LOST"
    NONE = "NONE"  # order never shipped — no shipment record at all


_LAST_LOCATION = {
    ShipmentScenario.IN_TRANSIT: "Regional sort facility",
    ShipmentScenario.EXCEPTION: "Held at carrier depot — address issue",
    ShipmentScenario.LOST: "Last scan at origin hub",
}


def create_delayed_order(
    db: Session,
    delay_days: int,
    shipment_scenario: ShipmentScenario,
    customer_id: int | None = None,
    customer_email: str | None = None,
) -> dict:
    """Creates the order (+ shipment unless NONE), publishes ORDER_DELAYED.

    customer_email: place the order for the customer with this email,
    creating them if needed — so the demo's notifications are addressed to an
    inbox you can check. Takes precedence over a random customer; can't be
    combined with customer_id.

    Raises ValueError if the referenced customer doesn't exist or the
    database has no customers/products to build the order from.
    """
    if customer_id is not None and customer_email:
        raise ValueError("Give either customer_id or customer_email, not both")

    if customer_email:
        customer = _get_or_create_customer(db, customer_email)
    elif customer_id is not None:
        customer = db.get(Customer, customer_id)
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found")
    else:
        customer = _random_row(db, Customer)
        if customer is None:
            raise ValueError("No customers in the database — run `make seed` first")

    product = _random_row(db, Product)
    if product is None:
        raise ValueError("No products in the database — run `make seed` first")

    today = datetime.now(UTC).date()
    now = datetime.now(UTC).replace(tzinfo=None)
    quantity = random.randint(1, 3)

    order = Order(
        customer_id=customer.id,
        expected_delivery=today - timedelta(days=delay_days),
        status=(
            OrderStatus.PROCESSING
            if shipment_scenario == ShipmentScenario.NONE
            else OrderStatus.SHIPPED
        ),
        total_amount=product.price * quantity,
    )
    db.add(order)
    db.add(
        OrderItem(
            order=order, product=product, quantity=quantity, unit_price=product.price
        )
    )

    if shipment_scenario != ShipmentScenario.NONE:
        db.add(
            Shipment(
                order=order,
                carrier=random.choice(DEMO_CARRIERS),
                tracking_number=f"DEMO-{uuid4().hex[:12].upper()}",
                status=ShipmentStatus(shipment_scenario.value),
                last_location=_LAST_LOCATION[shipment_scenario],
                last_updated=now - timedelta(days=min(delay_days, 3)),
            )
        )

    db.commit()
    db.refresh(order)

    event = Event(
        event_id=str(uuid4()),
        event_type=EventType.ORDER_DELAYED,
        occurred_at=datetime.now(UTC),
        source="demo-simulator",
        data={
            "order_id": order.id,
            "customer_id": order.customer_id,
            "expected_delivery": order.expected_delivery.isoformat(),
            "delay_days": delay_days,
        },
    )
    message_id = publish_event(event)

    # Mark it published for today so a later "Publish to event stream" run of
    # the order monitor doesn't send this same order through a second time.
    redis_client.set(delayed_order_dedupe_key(order.id, today), "1", ex=86400)

    logger.info(
        "Demo delayed order created",
        extra={
            "order_id": order.id,
            "event_id": event.event_id,
            "delay_days": delay_days,
            "shipment_scenario": shipment_scenario.value,
        },
    )

    return {
        "order_id": order.id,
        "customer_id": order.customer_id,
        "event_id": event.event_id,
        "message_id": message_id,
    }


def create_customer_ticket(
    db: Session,
    subject: str,
    message: str,
    priority: TicketPriority = TicketPriority.MEDIUM,
    order_id: int | None = None,
    customer_email: str | None = None,
) -> dict:
    """Files a support ticket as the order's customer and publishes
    TICKET_CREATED, the same event action_service publishes for agent-created
    tickets.

    Which order: order_id if given; else, with customer_email, that
    customer's most recent order; else a random existing order. If both are
    given, the order must belong to that customer.

    Raises ValueError if the order/customer doesn't exist, they don't match,
    or there's no order to file against.
    """
    customer = None
    if customer_email:
        customer = _find_customer(db, customer_email)
        if customer is None:
            raise ValueError(
                f"No customer with email {customer_email} — simulate a delayed "
                "order for that email first, so they have an order to complain about"
            )

    if order_id is not None:
        order = db.get(Order, order_id)
        if order is None:
            raise ValueError(f"Order {order_id} not found")
        if customer is not None and order.customer_id != customer.id:
            raise ValueError(f"Order {order_id} doesn't belong to {customer_email}")
    elif customer is not None:
        order = (
            db.query(Order)
            .filter(Order.customer_id == customer.id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .first()
        )
        if order is None:
            raise ValueError(f"{customer_email} has no orders to complain about")
    else:
        order = _random_row(db, Order)
        if order is None:
            raise ValueError("No orders in the database — run `make seed` first")

    ticket = SupportTicket(
        customer_id=order.customer_id,
        order_id=order.id,
        subject=subject,
        message=message,
        priority=priority.value,
        status=TicketStatus.OPEN.value,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    event = Event(
        event_id=str(uuid4()),
        event_type=EventType.TICKET_CREATED,
        occurred_at=datetime.now(UTC),
        source="demo-simulator",
        data={
            "ticket_id": ticket.id,
            "order_id": order.id,
            "customer_id": order.customer_id,
            "subject": subject,
            "message": message,
            "priority": priority.value,
        },
    )
    message_id = publish_event(event)

    send_customer_email(
        db,
        order.customer_id,
        order.id,
        ticket_acknowledgement(
            customer_first_name(db, order.customer_id),
            ticket.id,
            order.id,
            about=f"your order #{order.id}: “{subject}”",
        ),
    )

    logger.info(
        "Demo customer ticket created",
        extra={
            "ticket_id": ticket.id,
            "order_id": order.id,
            "event_id": event.event_id,
        },
    )

    return {
        "ticket_id": ticket.id,
        "order_id": order.id,
        "customer_id": order.customer_id,
        "event_id": event.event_id,
        "message_id": message_id,
    }


def _find_customer(db: Session, email: str) -> Customer | None:
    return (
        db.query(Customer)
        .filter(func.lower(Customer.email) == email.strip().lower())
        .first()
    )


def _get_or_create_customer(db: Session, email: str) -> Customer:
    customer = _find_customer(db, email)
    if customer is not None:
        return customer

    email = email.strip()
    # "jane.doe@example.com" -> "Jane Doe": the agent greets customers by
    # name in drafted messages, so give it something sensible.
    local_part = email.split("@", 1)[0]
    name = " ".join(
        w.capitalize() for w in local_part.replace("_", ".").split(".") if w
    )
    customer = Customer(name=(name or local_part)[:150], email=email)
    db.add(customer)
    db.flush()
    return customer


def _random_row(db: Session, model):
    count = db.query(model).count()
    if count == 0:
        return None
    return db.query(model).order_by(model.id).offset(random.randrange(count)).first()
