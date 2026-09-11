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

def _decision(**overrides) -> AgentDecision:
    fields = {
        "severity": "HIGH",
        "resolution": "ESCALATE",
        "reasoning": "Shipment has not moved in 10 days.",
        "customer_message": "We're sorry for the delay.",
        "requires_human": True,
    }
    fields.update(overrides)
    return AgentDecision(**fields)

class TestExecuteDecisionEscalate:
    def test_creates_ticket_and_publishes_event(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(resolution="ESCALATE", severity="CRITICAL")

        with patch.object(action_service, "publish_event") as mock_publish:
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert "escalation_ticket_created" in result["actions"]
        assert result["ticket_id"] is not None

        ticket = db_session.get(SupportTicket, result["ticket_id"])
        assert ticket is not None
        assert ticket.status == TicketStatus.OPEN
        assert ticket.customer_id == customer.id
        assert ticket.order_id == order.id

        mock_publish.assert_called_once()
        published_event = mock_publish.call_args[0][0]
        assert published_event.event_type == "TICKET_CREATED"
        assert published_event.data["ticket_id"] == ticket.id
        assert hasattr(published_event, "trace_context")

class TestExecuteDecisionContactCustomer:
    def test_creates_ticket_with_customer_message(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(
            resolution="CONTACT_CUSTOMER",
            severity="MEDIUM",
            customer_message="Your order is running a bit behind schedule."
        )

        with patch.object(action_service, "publish_event"):
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert "customer_contact_ticket_created" in result["actions"]
        ticket = db_session.get(SupportTicket, result["ticket_id"])
        assert ticket.message == "Your order is running a bit behind schedule."

    def test_falls_back_to_reasoning_when_no_customer_message(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(
            resolution="CONTACT_CUSTOMER",
            severity="MEDIUM",
            customer_message=None,
            reasoning="Delay confirmed via carrier tracking."
        )

        with patch.object(action_service, "publish_event"):
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        ticket = db_session.get(SupportTicket, result["ticket_id"])
        assert ticket.message == "Delay confirmed via carrier tracking."

class TestExecuteDecisionNoTicketBranches:
    """TRACK_SHIPMENT and CONTACT_CARRIER are currently TODO stubs — they
    don't call a carrier API, they just log that something happened. These
    tests document that current (limited) behavior: no ticket, no event,
    just an action label. If a real carrier integration gets added later,
    these tests should start failing here, which is exactly the point —
    it means someone needs to come update this test to match the new
    (real) behavior instead of the gap going unnoticed.
    """

    def test_track_shipment_creates_no_ticket(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(resolution="TRACK_SHIPMENT", severity="LOW", requires_human=False)

        with patch.object(action_service, "publish_event") as mock_publish:
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert result["actions"] == ["shipment_tracked"]
        assert result["ticket_id"] is None
        mock_publish.assert_not_called()

    def test_contact_carrier_creates_no_ticket(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(resolution="CONTACT_CARRIER", severity="HIGH", requires_human=True)

        with patch.object(action_service, "publish_event") as mock_publish:
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert result["actions"] == ["carrier_contacted"]
        assert result["ticket_id"] is None
        mock_publish.assert_not_called()

    def test_no_action_records_no_action_taken(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(resolution="NO_ACTION", severity="LOW", requires_human=False)

        with patch.object(action_service, "publish_event") as mock_publish:
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert result["actions"] == ["no_action_taken"]
        assert result["ticket_id"] is None
        mock_publish.assert_not_called()