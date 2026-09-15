from uuid import uuid4

from app.api.admin import list_pending_approvals
from app.models.customer import Customer
from app.models.human_approval import HumanApproval
from app.models.order import Order


def _make_customer(db_session) -> Customer:
    unique = uuid4().hex[:8]
    customer = Customer(name="Test Customer", email=f"test-{unique}@example.com")
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


def _make_order(db_session, customer_id: int) -> Order:
    order = Order(customer_id=customer_id, total_amount=42, expected_delivery=None)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def _make_approval(db_session, customer_id: int, order_id: int) -> HumanApproval:
    approval = HumanApproval(
        event_id=str(uuid4()),
        order_id=order_id,
        customer_id=customer_id,
        agent_name="delayed_order_agent",
        decision={"severity": "HIGH", "resolution": "ESCALATE"},
    )
    db_session.add(approval)
    db_session.commit()
    db_session.refresh(approval)
    return approval


def test_list_pending_approvals_includes_customer_email(db_session):
    customer = _make_customer(db_session)
    order = _make_order(db_session, customer.id)
    _make_approval(db_session, customer.id, order.id)

    result = list_pending_approvals(db=db_session)

    assert len(result) == 1
    assert result[0]["customer_email"] == customer.email
