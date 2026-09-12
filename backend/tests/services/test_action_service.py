from unittest.mock import patch
from uuid import uuid4

from app.agents.models import AgentDecision
from app.models.customer import Customer
from app.models.notification import Notification
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
        "customer_message": None,
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
            customer_message="Your order is running a bit behind schedule.",
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
            reasoning="Delay confirmed via carrier tracking.",
        )

        with patch.object(action_service, "publish_event"):
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        ticket = db_session.get(SupportTicket, result["ticket_id"])
        assert ticket.message == "Delay confirmed via carrier tracking."


class TestExecuteDecisionTrackShipment:
    """TRACK_SHIPMENT has no real carrier API integrated. Rather than a
    silent no-op that just logs "shipment_tracked" as if something
    happened, it now creates a real internal follow-up ticket — and,
    importantly, does NOT publish a triage event, since there's no
    customer message here for the triage agent to classify."""

    def test_creates_internal_ticket_without_triaging(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(resolution="TRACK_SHIPMENT", severity="LOW", requires_human=False)

        with patch.object(action_service, "publish_event") as mock_publish:
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert result["actions"] == ["shipment_tracking_ticket_created"]
        assert result["ticket_id"] is not None

        ticket = db_session.get(SupportTicket, result["ticket_id"])
        assert "track shipment" in ticket.subject.lower()
        assert ticket.status == TicketStatus.OPEN

        mock_publish.assert_not_called()


class TestExecuteDecisionContactCarrier:
    def test_creates_internal_ticket_without_triaging(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(resolution="CONTACT_CARRIER", severity="HIGH", requires_human=True)

        with patch.object(action_service, "publish_event") as mock_publish:
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert result["actions"] == ["carrier_contact_ticket_created"]
        assert result["ticket_id"] is not None

        ticket = db_session.get(SupportTicket, result["ticket_id"])
        assert "contact carrier" in ticket.subject.lower()

        mock_publish.assert_not_called()


class TestExecuteDecisionNoAction:
    def test_records_no_action_taken_and_creates_no_ticket(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(resolution="NO_ACTION", severity="LOW", requires_human=False)

        with patch.object(action_service, "publish_event") as mock_publish:
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert result["actions"] == ["no_action_taken"]
        assert result["ticket_id"] is None
        mock_publish.assert_not_called()


class TestCustomerNotification:
    """A customer_message triggers a notification regardless of which
    resolution branch fired — the two are independent decisions the
    agent makes (what to do internally vs. whether to tell the
    customer)."""

    def test_sends_notification_when_customer_message_present(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(
            resolution="TRACK_SHIPMENT",
            customer_message="We're keeping an eye on your shipment.",
        )

        with patch.object(action_service, "publish_event"):
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert "customer_notified" in result["actions"]
        notifications = db_session.query(Notification).filter_by(customer_id=customer.id).all()
        assert len(notifications) == 1
        assert notifications[0].content == "We're keeping an eye on your shipment."
        assert notifications[0].status == "SENT"
        assert notifications[0].recipient == customer.email

    def test_no_notification_when_no_customer_message(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(resolution="NO_ACTION", customer_message=None)

        with patch.object(action_service, "publish_event"):
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert "customer_notified" not in result["actions"]
        assert db_session.query(Notification).filter_by(customer_id=customer.id).count() == 0

    def test_notification_failure_does_not_break_execution(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = _decision(resolution="NO_ACTION", customer_message="Hello!")

        from app.services import notification_service

        def _raise(*args, **kwargs):
            raise RuntimeError("smtp down")

        with (
            patch.object(action_service, "publish_event"),
            patch.dict(notification_service._BACKENDS, {"log": _raise}),
        ):
            result = action_service.execute_decision(
                db=db_session, order_id=order.id, customer_id=customer.id, decision=decision
            )

        assert "customer_notification_failed" in result["actions"]
        notification = db_session.query(Notification).filter_by(customer_id=customer.id).one()
        assert notification.status == "FAILED"
        assert notification.error == "smtp down"