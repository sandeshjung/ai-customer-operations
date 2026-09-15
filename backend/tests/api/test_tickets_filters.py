from uuid import uuid4

from app.api.tickets import list_tickets
from app.models.customer import Customer
from app.models.support_ticket import SupportTicket


def _make_customer(db_session) -> Customer:
    unique = uuid4().hex[:8]
    customer = Customer(name="Test Customer", email=f"test-{unique}@example.com")
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


def _make_ticket(db_session, customer_id: int, subject: str) -> SupportTicket:
    ticket = SupportTicket(
        customer_id=customer_id,
        subject=subject,
        message="test message",
    )
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


def test_list_tickets_filters_by_customer_id(db_session):
    customer_a = _make_customer(db_session)
    customer_b = _make_customer(db_session)

    _make_ticket(db_session, customer_a.id, "A's ticket")
    _make_ticket(db_session, customer_b.id, "B's ticket")

    result = list_tickets(status=None, customer_id=customer_a.id, db=db_session)

    assert len(result) == 1
    assert result[0]["customer_id"] == customer_a.id
    assert result[0]["subject"] == "A's ticket"


def test_list_tickets_includes_customer_email(db_session):
    customer = _make_customer(db_session)
    _make_ticket(db_session, customer.id, "A ticket")

    result = list_tickets(status=None, customer_id=customer.id, db=db_session)

    assert result[0]["customer_email"] == customer.email


def test_list_tickets_without_customer_id_returns_all(db_session):
    customer_a = _make_customer(db_session)
    customer_b = _make_customer(db_session)

    _make_ticket(db_session, customer_a.id, "A's ticket")
    _make_ticket(db_session, customer_b.id, "B's ticket")

    result = list_tickets(status=None, customer_id=None, db=db_session)

    assert len(result) == 2


def test_list_tickets_customer_id_with_no_matches_returns_empty(db_session):
    customer = _make_customer(db_session)
    _make_ticket(db_session, customer.id, "A ticket")

    result = list_tickets(status=None, customer_id=customer.id + 999, db=db_session)

    assert result == []
