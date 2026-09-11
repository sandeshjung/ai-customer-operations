from unittest.mock import patch
from uuid import uuid4

import pytest

from app.models.customer import Customer
from app.models.human_approval import ApprovalStatus, HumanApproval
from app.models.order import Order
from app.services import approval_service

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

def _sample_decision(**overrides) -> dict:
    decision = {
        "severity": "HIGH",
        "resolution": "ESCALATE",
        "reasoning": "Shipment has not moved in 10 days.",
        "customer_message": "We're sorry for the delay.",
        "requires_human": True,
        "evidence": [],
        "trace_id": "abc123",
        "trace_context": {"traceparent": "00-abc123-def456-01"},
    }
    decision.update(overrides)
    return decision

def _make_pending_approval(db_session, **decision_overrides) -> HumanApproval:
    customer, order = _make_customer_and_order(db_session)
    approval = HumanApproval(
        event_id="evt-1",
        order_id=order.id,
        customer_id=customer.id,
        agent_name="delayed_order_agent",
        decision=_sample_decision(**decision_overrides),
        status=ApprovalStatus.PENDING
    )
    db_session.add(approval)
    db_session.commit()
    db_session.refresh(approval)
    return approval

class TestCreateApproval:
    def test_persists_as_pending(self, db_session):
        customer, order = _make_customer_and_order(db_session)

        from app.agents.models import AgentDecision

        decision = AgentDecision.model_validate(_sample_decision())

        approval = approval_service.create_approval(
            db=db_session,
            event_id="evt-1",
            order_id=order.id,
            customer_id=customer.id,
            agent_name="delayed_order_agent",
            decision=decision
        )

        assert approval.id is not None
        assert approval.status == ApprovalStatus.PENDING
        assert approval.decision["severity"] == "HIGH"

class TestGetPendingApprovals:
    def test_returns_only_pending(self, db_session):
        pending = _make_pending_approval(db_session)
        reviewed = _make_pending_approval(db_session)
        reviewed.status = ApprovalStatus.APPROVED
        db_session.commit()

        results = approval_service.get_pending_approvals(db_session)

        ids = [a.id for a in results]
        assert pending.id in ids
        assert reviewed.id not in ids

    def test_respects_limit(self, db_session):
        for _ in range(3):
            _make_pending_approval(db_session)

        results = approval_service.get_pending_approvals(db_session, limit=2)

        assert len(results) == 2

class TestApprove:
    def test_marks_approved_and_executes(self, db_session):
        approval = _make_pending_approval(db_session)

        with patch.object(
            approval_service,
            "execute_decision",
            return_value={"actions": ["escalation_ticket_created"], "ticket_id": 99},
        ) as mock_execute:
            result_approval, result = approval_service.approve(
                db=db_session, approval_id=approval.id, reviewer="alice"
            )

        assert result_approval.status == ApprovalStatus.APPROVED
        assert result_approval.reviewed_by == "alice"
        assert result_approval.reviewed_at is not None
        assert result["ticket_id"] == 99
        mock_execute.assert_called_once()

        _, call_kwargs = mock_execute.call_args
        assert call_kwargs["order_id"] == approval.order_id
        assert call_kwargs["customer_id"] == approval.customer_id
        assert call_kwargs["decision"].severity == "HIGH"

    def test_raises_if_not_found(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            approval_service.approve(db=db_session, approval_id=999, reviewer="alice")

    def test_raises_if_already_reviewed(self, db_session):
        approval = _make_pending_approval(db_session)
        approval.status = ApprovalStatus.APPROVED
        db_session.commit()

        with pytest.raises(ValueError, match="already"):
            approval_service.approve(db=db_session, approval_id=approval.id, reviewer="alice")

    def test_links_to_original_trace_without_raising(self, db_session):
        """Regression guard: approve() reconstructs a Link from the stored
        trace_context. This should never blow up even when tracing is
        effectively a no-op (the default in tests, since setup_tracing()
        is never called here)."""
        approval = _make_pending_approval(db_session)

        with patch.object(approval_service, "execute_decision", return_value={"actions": []}):
            approval_service.approve(db=db_session, approval_id=approval.id, reviewer="alice")

    def test_missing_trace_context_does_not_raise(self, db_session):
        """A decision with no trace_context at all (e.g. from before this
        field existed) should still approve cleanly."""
        approval = _make_pending_approval(db_session, trace_context=None, trace_id=None)

        with patch.object(approval_service, "execute_decision", return_value={"actions": []}):
            result_approval, _ = approval_service.approve(
                db=db_session, approval_id=approval.id, reviewer="alice"
            )

        assert result_approval.status == ApprovalStatus.APPROVED


class TestReject:
    def test_returns_approval_with_id(self, db_session):
        approval = _make_pending_approval(db_session)

        result = approval_service.reject(db=db_session, approval_id=approval.id, reviewer="bob")

        assert result is not None
        assert result.id == approval.id

    def test_marks_rejected(self, db_session):
        approval = _make_pending_approval(db_session)

        result = approval_service.reject(
            db=db_session, approval_id=approval.id, reviewer="bob", notes="not needed"
        )

        assert result.status == ApprovalStatus.REJECTED
        assert result.reviewed_by == "bob"
        assert result.reviewer_notes == "not needed"
        assert result.reviewed_at is not None

    def test_does_not_execute_the_decision(self, db_session):
        approval = _make_pending_approval(db_session)

        with patch.object(approval_service, "execute_decision") as mock_execute:
            approval_service.reject(db=db_session, approval_id=approval.id, reviewer="bob")

        mock_execute.assert_not_called()

    def test_raises_if_not_found(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            approval_service.reject(db=db_session, approval_id=999, reviewer="bob")
            