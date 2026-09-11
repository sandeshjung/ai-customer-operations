from unittest.mock import patch
from uuid import uuid4

from app.agents.models import AgentDecision
from app.models.customer import Customer
from app.models.order import Order
from app.models.support_ticket import SupportTicket, TicketStatus
from app.services import action_service


def _make_customer_and_order(db_session) -> tuple[Customer, Order]:
    unique = uuid4().hex[:8]
    customer = Customer(name="Test Customer", email=f"test-{unique}@example.com")
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    order = Order(customer_id=customer.id, total_amount=42, expected_delivery=None)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    return customer, order