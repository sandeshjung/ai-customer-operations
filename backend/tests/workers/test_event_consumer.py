import sys
import types

def _install_rag_service_stub() -> None:
    fake_module = types.ModuleType("app.rag.service")
    fake_module.retrieve_policy = lambda query, limit=5: []
    sys.modules["app.rag.service"] = fake_module

_install_rag_service_stub()

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.customer import Customer
from app.models.order import Order
from app.workers import event_consumer

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

def _order_delayed_event(order_id: int, delay_days: int = 10, **overrides) -> dict:
    event = {
        "event_id": "evt-1",
        "event_type": "ORDER_DELAYED",
        "data": {"order_id": order_id, "delay_days": delay_days},
        "trace_context": {},
    }
    event.update(overrides)
    return event

def _ticket_created_event(ticket_id: int, **overrides) -> dict:
    event = {
        "event_id": "evt-2",
        "event_type": "TICKET_CREATED",
        "data": {"ticket_id": ticket_id},
        "trace_context": {}
    }
    event.update(overrides)
    return event

@pytest.fixture(autouse=True)
def _patch_session_local(db_session):
    """process_event calls SessionLocal() itself — route that at the
    test's in-memory session instead of a real Postgres connection."""
    with patch.object(event_consumer, "SessionLocal", return_value=db_session):
        yield

class TestOrderDelayedRequiresHuman:
    def test_creates_approval_and_skips_auto_execute(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        customer_id, order_id = customer.id, order.id
        decision = MagicMock(requires_human=True)

        with (
            patch.object(event_consumer, "investigate_delayed_order", return_value=decision) as mock_investigate,
            patch.object(event_consumer, "create_approval") as mock_create_approval,
            patch.object(event_consumer, "execute_decision") as mock_execute,
        ):
            event_consumer.process_event(_order_delayed_event(order_id, delay_days=15))

        mock_investigate.assert_called_once_with(
            db=db_session, order_id=order_id, delay_days=15, event_id="evt-1"
        )
        mock_create_approval.assert_called_once_with(
            db=db_session,
            event_id="evt-1",
            order_id=order_id,
            customer_id=customer_id,
            agent_name="delayed_order_agent",
            decision=decision,
        )
        mock_execute.assert_not_called()


class TestOrderDelayedAutoExecute:
    def test_executes_decision_when_human_not_required(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        customer_id, order_id = customer.id, order.id
        decision = MagicMock(requires_human=False)

        with (
            patch.object(event_consumer, "investigate_delayed_order", return_value=decision),
            patch.object(event_consumer, "create_approval") as mock_create_approval,
            patch.object(event_consumer, "execute_decision") as mock_execute,
        ):
            event_consumer.process_event(_order_delayed_event(order_id))

        mock_execute.assert_called_once_with(
            db=db_session, order_id=order_id, customer_id=customer_id, decision=decision
        )
        mock_create_approval.assert_not_called()


class TestOrderDelayedMissingCustomer:
    def test_returns_early_without_approving_or_executing(self, db_session):
        """order_id that doesn't exist in the DB -> get_order returns
        {"error": ...} -> no customer_id -> should bail out cleanly rather
        than crash or silently proceed with customer_id=None."""
        decision = MagicMock(requires_human=True)
        nonexistent_order_id = 999999

        with (
            patch.object(event_consumer, "investigate_delayed_order", return_value=decision),
            patch.object(event_consumer, "create_approval") as mock_create_approval,
            patch.object(event_consumer, "execute_decision") as mock_execute,
        ):
            event_consumer.process_event(_order_delayed_event(nonexistent_order_id))

        mock_create_approval.assert_not_called()
        mock_execute.assert_not_called()


class TestTicketCreated:
    def test_dispatches_to_process_ticket(self, db_session):
        with patch.object(event_consumer, "process_ticket") as mock_process_ticket:
            event_consumer.process_event(_ticket_created_event(ticket_id=77))

        mock_process_ticket.assert_called_once_with(db=db_session, ticket_id=77, event_id="evt-2")


class TestSessionCleanup:
    def test_db_closed_even_if_investigation_raises(self, db_session):
        customer, order = _make_customer_and_order(db_session)

        with (
            patch.object(event_consumer, "investigate_delayed_order", side_effect=RuntimeError("boom")),
            patch.object(db_session, "close", wraps=db_session.close) as mock_close,
        ):
            with pytest.raises(RuntimeError, match="boom"):
                event_consumer.process_event(_order_delayed_event(order.id))

        mock_close.assert_called_once()

    def test_db_closed_on_success_too(self, db_session):
        customer, order = _make_customer_and_order(db_session)
        decision = MagicMock(requires_human=False)

        with (
            patch.object(event_consumer, "investigate_delayed_order", return_value=decision),
            patch.object(event_consumer, "execute_decision"),
            patch.object(db_session, "close", wraps=db_session.close) as mock_close,
        ):
            event_consumer.process_event(_order_delayed_event(order.id))

        mock_close.assert_called_once()