import sys
import types
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.agents.models import TicketPriority as DecisionPriority
from app.models.customer import Customer
from app.models.support_ticket import SupportTicket, TicketPriority, TicketStatus
from app.services import triage_service


def _stub_rag_service(results=None):
    """Build a fake app.rag.service module and install it in sys.modules.

    We can't use unittest.mock.patch("app.rag.service.retrieve_policy", ...)
    here: patch() has to import app.rag.service to resolve that target
    string, and *that* import eagerly loads a real HuggingFace embedding
    model as a side effect (see app.rag.vector_store) — which fails
    without network access, before our mock ever gets applied. Installing
    a stub module directly in sys.modules sidesteps the real import
    entirely, since `from app.rag.service import retrieve_policy` inside
    process_ticket() just looks the name up on whatever's already in
    sys.modules under that name.
    """
    fake_module = types.ModuleType("app.rag.service")
    fake_module.retrieve_policy = lambda query, limit=5: results or []
    return fake_module


def _make_ticket(db_session, **overrides) -> SupportTicket:
    unique = uuid4().hex[:8]
    customer = Customer(name="Test Customer", email=f"test-{unique}@example.com")
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    fields = {
        "customer_id": customer.id,
        "order_id": None,
        "subject": "Where is my package?",
        "message": "It's been two weeks and nothing has arrived.",
        "status": TicketStatus.OPEN,
        "priority": TicketPriority.LOW,
    }
    fields.update(overrides)
    ticket = SupportTicket(**fields)
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


def _fake_decision(**overrides):
    fields = {
        "intent": "MISSING_PACKAGE",
        "priority": DecisionPriority.HIGH,
        "sentiment": "FRUSTRATED",
        "action": "ESCALATE",
        "reasoning": "Customer has waited two weeks with no update.",
        "requires_human": True,
        "confidence": 0.9,
        "trace_id": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestProcessTicket:
    def test_upgrades_priority_when_triage_says_higher(self, db_session):
        ticket = _make_ticket(db_session, priority=TicketPriority.LOW)
        decision = _fake_decision(priority=DecisionPriority.HIGH, action="ESCALATE")

        with (
            patch.dict(sys.modules, {"app.rag.service": _stub_rag_service()}),
            patch.object(triage_service, "triage_graph") as mock_graph,
        ):
            mock_graph.invoke.return_value = {"decision": decision}
            result = triage_service.process_ticket(db=db_session, ticket_id=ticket.id, event_id="evt-1")

        db_session.refresh(ticket)
        assert ticket.priority == TicketPriority.HIGH
        assert result is decision

    def test_does_not_downgrade_priority(self, db_session):
        ticket = _make_ticket(db_session, priority=TicketPriority.CRITICAL)
        decision = _fake_decision(priority=DecisionPriority.LOW, action="AUTO_RESPOND")

        with (
            patch.dict(sys.modules, {"app.rag.service": _stub_rag_service()}),
            patch.object(triage_service, "triage_graph") as mock_graph,
        ):
            mock_graph.invoke.return_value = {"decision": decision}
            triage_service.process_ticket(db=db_session, ticket_id=ticket.id, event_id="evt-1")

        db_session.refresh(ticket)
        assert ticket.priority == TicketPriority.CRITICAL

    def test_auto_resolves_on_resolve_action(self, db_session):
        ticket = _make_ticket(db_session, status=TicketStatus.OPEN)
        decision = _fake_decision(action="RESOLVE", requires_human=False, priority=DecisionPriority.LOW)

        with (
            patch.dict(sys.modules, {"app.rag.service": _stub_rag_service()}),
            patch.object(triage_service, "triage_graph") as mock_graph,
        ):
            mock_graph.invoke.return_value = {"decision": decision}
            triage_service.process_ticket(db=db_session, ticket_id=ticket.id, event_id="evt-1")

        db_session.refresh(ticket)
        assert ticket.status == TicketStatus.RESOLVED

    def test_does_not_resolve_if_requires_human(self, db_session):
        """A RESOLVE action that still requires human review shouldn't
        silently close the ticket."""
        ticket = _make_ticket(db_session, status=TicketStatus.OPEN)
        decision = _fake_decision(action="RESOLVE", requires_human=True, priority=DecisionPriority.LOW)

        with (
            patch.dict(sys.modules, {"app.rag.service": _stub_rag_service()}),
            patch.object(triage_service, "triage_graph") as mock_graph,
        ):
            mock_graph.invoke.return_value = {"decision": decision}
            triage_service.process_ticket(db=db_session, ticket_id=ticket.id, event_id="evt-1")

        db_session.refresh(ticket)
        assert ticket.status == TicketStatus.OPEN

    def test_missing_ticket_returns_none_without_raising(self, db_session):
        with patch.dict(sys.modules, {"app.rag.service": _stub_rag_service()}):
            result = triage_service.process_ticket(db=db_session, ticket_id=99999, event_id="evt-1")

        assert result is None