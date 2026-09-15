from uuid import uuid4

from app.api.admin import list_notifications
from app.models.customer import Customer
from app.models.notification import Notification, NotificationStatus


def _make_customer(db_session) -> Customer:
    unique = uuid4().hex[:8]
    customer = Customer(name="Test Customer", email=f"test-{unique}@example.com")
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


def _make_notification(db_session, customer_id: int, **overrides) -> Notification:
    notification = Notification(
        customer_id=customer_id,
        recipient=overrides.pop("recipient", "customer@example.com"),
        subject=overrides.pop("subject", "An update on your order"),
        content=overrides.pop("content", "Your order is delayed."),
        status=overrides.pop("status", NotificationStatus.SENT),
    )
    db_session.add(notification)
    db_session.commit()
    db_session.refresh(notification)
    return notification


def test_list_notifications_returns_most_recent_first(db_session):
    customer = _make_customer(db_session)
    first = _make_notification(db_session, customer.id, subject="First")
    second = _make_notification(db_session, customer.id, subject="Second")

    result = list_notifications(db=db_session)

    assert [n["id"] for n in result] == [second.id, first.id]


def test_list_notifications_includes_failure_details(db_session):
    customer = _make_customer(db_session)
    _make_notification(
        db_session,
        customer.id,
        status=NotificationStatus.FAILED,
        recipient="unknown",
    )

    result = list_notifications(db=db_session)

    assert result[0]["status"] == NotificationStatus.FAILED
    assert result[0]["recipient"] == "unknown"


def test_list_notifications_respects_limit(db_session):
    customer = _make_customer(db_session)
    for i in range(5):
        _make_notification(db_session, customer.id, subject=f"Notice {i}")

    result = list_notifications(limit=2, db=db_session)

    assert len(result) == 2
