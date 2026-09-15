from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
import pytest
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

    def test_unknown_customer_records_failed_notification_without_raising(
        self, db_session
    ):
        notification = notification_service.send_notification(
            db=db_session, customer_id=999999, content="test"
        )

        assert notification.status == NotificationStatus.FAILED
        assert notification.error == "Customer not found"
        assert notification.recipient == "unknown"

    def test_unknown_backend_falls_back_to_log_instead_of_dropping_message(
        self, db_session
    ):
        customer = _make_customer(db_session)

        with patch.object(
            notification_service.settings, "NOTIFICATION_BACKEND", "sendgrid"
        ):
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

        notification_service.send_notification(
            db=db_session, customer_id=customer.id, content="first"
        )
        notification_service.send_notification(
            db=db_session, customer_id=customer.id, content="second"
        )

        rows = db_session.query(Notification).filter_by(customer_id=customer.id).all()
        assert len(rows) == 2
        assert {r.content for r in rows} == {"first", "second"}


class TestMailjetDemoBackend:
    """Not wired into the default flow (see the commented call site in
    send_notification()) — these test it directly since it's still real,
    reachable code that should work correctly if/when someone uncomments it."""

    def test_send_via_mailjet_posts_expected_payload(self):
        mock_response = Mock(status_code=200)
        mock_response.raise_for_status = Mock()

        with (
            patch.object(notification_service.settings, "MAILJET_API_KEY", "key"),
            patch.object(notification_service.settings, "MAILJET_API_SECRET", "secret"),
            patch.object(
                notification_service.settings,
                "MAILJET_SENDER_EMAIL",
                "support@example.com",
            ),
            patch.object(
                notification_service.httpx, "post", return_value=mock_response
            ) as mock_post,
        ):
            notification_service._send_via_mailjet(
                "customer@example.com", "Shipping update", "Your order shipped!"
            )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.mailjet.com/v3.1/send"
        assert kwargs["auth"] == ("key", "secret")
        message = kwargs["json"]["Messages"][0]
        assert message["From"]["Email"] == "support@example.com"
        assert message["To"] == [{"Email": "customer@example.com"}]
        assert message["Subject"] == "Shipping update"
        assert message["TextPart"] == "Your order shipped!"
        mock_response.raise_for_status.assert_called_once()

    def test_send_via_mailjet_raises_on_error_response(self):
        mock_response = Mock(status_code=401)
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized", request=None, response=mock_response
            )
        )

        with (
            patch.object(
                notification_service.httpx, "post", return_value=mock_response
            ),
            pytest.raises(httpx.HTTPStatusError),
        ):
            notification_service._send_via_mailjet(
                "customer@example.com", "Subject", "Body"
            )

    def test_demo_send_via_mailjet_swallows_failures(self):
        with patch.object(
            notification_service,
            "_send_via_mailjet",
            side_effect=RuntimeError("bad credentials"),
        ):
            notification_service._demo_send_via_mailjet(
                "customer@example.com", "Subject", "Body"
            )  # must not raise
