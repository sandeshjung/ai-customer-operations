import threading
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
import app.models  # noqa: F401 - registers all tables on Base.metadata
from app.models.customer import Customer
from app.models.human_approval import ApprovalStatus, HumanApproval
from app.models.order import Order
from app.services import approval_service


@pytest.fixture()
def shared_engine(tmp_path):
    """Use a single on-disk SQLite database so all sessions and threads
    operate against the same row set without SQLite creating a distinct
    in-memory database per connection. The in-memory case with a single
    shared connection can trigger thread-bound connection errors and
    makes the concurrency test meaningless."""
    db_path = tmp_path / "approval_concurrency.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(shared_engine):
    return sessionmaker(bind=shared_engine, autoflush=False, autocommit=False)


def _make_pending_approval(session_factory) -> int:
    db = session_factory()
    unique = uuid4().hex[:8]
    customer = Customer(name="Test Customer", email=f"test-{unique}@example.com")
    db.add(customer)
    db.commit()
    db.refresh(customer)

    order = Order(customer_id=customer.id, total_amount=42, expected_delivery=None)
    db.add(order)
    db.commit()
    db.refresh(order)

    approval = HumanApproval(
        event_id="evt-1",
        order_id=order.id,
        customer_id=customer.id,
        agent_name="delayed_order_agent",
        decision={
            "severity": "HIGH",
            "resolution": "ESCALATE",
            "reasoning": "test",
            "customer_message": None,
            "requires_human": True,
            "evidence": [],
            "trace_id": None,
            "trace_context": None,
        },
        status=ApprovalStatus.PENDING,
    )
    db.add(approval)
    db.commit()
    approval_id = approval.id
    db.close()
    return approval_id


class TestApproveConcurrency:
    def test_only_one_of_two_concurrent_approvals_wins(self, session_factory):
        approval_id = _make_pending_approval(session_factory)

        outcomes = []
        outcomes_lock = threading.Lock()
        start_barrier = threading.Barrier(2)

        def _try_approve(reviewer: str):
            db = session_factory()
            try:
                # Barrier makes both threads call approve() at essentially
                # the same instant, instead of one sneaking in first just
                # because it got scheduled a moment earlier.
                start_barrier.wait(timeout=5)
                try:
                    from unittest.mock import patch

                    # execute_decision does real ticket/notification work
                    # we don't need for this test — mock it so we're
                    # purely testing the claim race, not action_service.
                    with patch.object(
                        approval_service, "execute_decision", return_value={"actions": [], "ticket_id": 1}
                    ):
                        approval_service.approve(db=db, approval_id=approval_id, reviewer=reviewer)
                    with outcomes_lock:
                        outcomes.append(("won", reviewer))
                except ValueError as exc:
                    with outcomes_lock:
                        outcomes.append(("lost", reviewer, str(exc)))
            finally:
                db.close()

        threads = [
            threading.Thread(target=_try_approve, args=("alice",)),
            threading.Thread(target=_try_approve, args=("bob",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(outcomes) == 2, f"both threads should finish, got: {outcomes}"

        wins = [o for o in outcomes if o[0] == "won"]
        losses = [o for o in outcomes if o[0] == "lost"]

        assert len(wins) == 1, f"exactly one approval should win the race, got: {outcomes}"
        assert len(losses) == 1, f"exactly one approval should lose the race, got: {outcomes}"
        assert "already" in losses[0][2]

        # Final DB state should reflect exactly one reviewer, not a mix.
        db = session_factory()
        final = db.get(HumanApproval, approval_id)
        assert final.status == ApprovalStatus.APPROVED
        assert final.reviewed_by == wins[0][1]
        db.close()

    def test_concurrent_approve_and_reject_only_one_wins(self, session_factory):
        """The same race between one person approving and another
        rejecting at the same moment — equally important to close, since
        "approved AND rejected" is an incoherent final state."""
        approval_id = _make_pending_approval(session_factory)

        outcomes = []
        outcomes_lock = threading.Lock()
        start_barrier = threading.Barrier(2)

        def _approve():
            from unittest.mock import patch

            db = session_factory()
            try:
                start_barrier.wait(timeout=5)
                try:
                    with patch.object(
                        approval_service, "execute_decision", return_value={"actions": [], "ticket_id": 1}
                    ):
                        approval_service.approve(db=db, approval_id=approval_id, reviewer="alice")
                    with outcomes_lock:
                        outcomes.append("approve_won")
                except ValueError:
                    with outcomes_lock:
                        outcomes.append("approve_lost")
            finally:
                db.close()

        def _reject():
            db = session_factory()
            try:
                start_barrier.wait(timeout=5)
                try:
                    approval_service.reject(db=db, approval_id=approval_id, reviewer="bob")
                    with outcomes_lock:
                        outcomes.append("reject_won")
                except ValueError:
                    with outcomes_lock:
                        outcomes.append("reject_lost")
            finally:
                db.close()

        threads = [threading.Thread(target=_approve), threading.Thread(target=_reject)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(outcomes) == 2
        wins = [o for o in outcomes if o.endswith("_won")]
        assert len(wins) == 1, f"exactly one of approve/reject should win, got: {outcomes}"

        db = session_factory()
        final = db.get(HumanApproval, approval_id)
        # Whichever won, the final status must match it exactly - not
        # some inconsistent mix of the two.
        expected_status = ApprovalStatus.APPROVED if wins[0] == "approve_won" else ApprovalStatus.REJECTED
        assert final.status == expected_status
        db.close()