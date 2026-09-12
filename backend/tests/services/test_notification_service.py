from unittest.mock import patch
from uuid import uuid4

from app.models.customer import Customer
from app.models.notification import Notification, NotificationStatus
from app.services import notification_service


def _make_customer(db_session, **overrides) -> Customer:
    unique = uuid4().hex[:8]
    fields = {"name": "Test Customer", "email": f"test-{unique}@example.com"}
    fields.update(overrides)
    customer = Customer(**fields)
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


class TestSendNotification:
    def test_persists_a_sent_notification_by_default(self, db_session):
        customer = _make_customer(db_session)

        notification = notification_service.send_notification(
            db=db_session,
            customer_id=customer.id,
            content="Your order shipped!",
            subject="Shipping update",
        )

        assert notification.id is not None
        assert notification.status == NotificationStatus.SENT
        assert notification.recipient == customer.email
        assert notification.content == "Your order shipped!"
        assert notification.subject == "Shipping update"
        assert notification.error is None

    def test_logs_via_default_backend_without_raising(self, db_session):
        customer = _make_customer(db_session)

        notification = notification_service.send_notification(
            db=db_session, customer_id=customer.id, content="test"
        )

        assert notification.status == NotificationStatus.SENT

    def test_records_order_id_when_provided(self, db_session):
        customer = _make_customer(db_session)

        notification = notification_service.send_notification(
            db=db_session, customer_id=customer.id, content="test", order_id=42
        )

        assert notification.order_id == 42

    def test_unknown_customer_records_failed_notification_without_raising(self, db_session):
        notification = notification_service.send_notification(
            db=db_session, customer_id=999999, content="test"
        )

        assert notification.status == NotificationStatus.FAILED
        assert notification.error == "Customer not found"
        assert notification.recipient == "unknown"

    def test_unknown_backend_falls_back_to_log_instead_of_dropping_message(self, db_session):
        customer = _make_customer(db_session)

        with patch.object(notification_service.settings, "NOTIFICATION_BACKEND", "sendgrid"):
            notification = notification_service.send_notification(
                db=db_session, customer_id=customer.id, content="test"
            )

        assert notification.status == NotificationStatus.SENT

    def test_backend_failure_is_recorded_not_raised(self, db_session):
        customer = _make_customer(db_session)

        def _raise(*args, **kwargs):
            raise ConnectionError("provider unreachable")

        with patch.dict(notification_service._BACKENDS, {"log": _raise}):
            notification = notification_service.send_notification(
                db=db_session, customer_id=customer.id, content="test"
            )

        assert notification.status == NotificationStatus.FAILED
        assert notification.error == "provider unreachable"

    def test_every_call_persists_its_own_row(self, db_session):
        """Notifications should accumulate as a history, not overwrite."""
        customer = _make_customer(db_session)

        notification_service.send_notification(db=db_session, customer_id=customer.id, content="first")
        notification_service.send_notification(db=db_session, customer_id=customer.id, content="second")

        rows = db_session.query(Notification).filter_by(customer_id=customer.id).all()
        assert len(rows) == 2
        assert {r.content for r in rows} == {"first", "second"}