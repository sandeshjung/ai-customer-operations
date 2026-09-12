from app.core.config import settings
from app.core.logging import get_logger
from app.models.customer import Customer
from app.models.notification import Notification, NotificationChannel, NotificationStatus

logger = get_logger(__name__)


def _send_via_log(recipient: str, subject: str | None, content: str) -> None:
    logger.info(
        "Notification (log backend - no real delivery)",
        extra={"recipient": recipient, "subject": subject, "content": content}
    )

_BACKENDS = {"log": _send_via_log}

def send_notification(
        db,
        customer_id: int,
        content: str,
        order_id: int | None = None,
        subject: str | None = None,
        channel: str = NotificationChannel.EMAIL
) -> Notification:

    customer = db.get(Customer, customer_id)
    if customer is None:
        logger.warning("Cannot notify - customer not found", extra={"customer_id": customer_id})
        notification = Notification(
            customer_id=customer_id,
            order_id=order_id,
            channel=channel,
            recipient="unknown",
            subject=subject,
            content=content,
            status=NotificationStatus.FAILED,
            error="Customer not found"
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification

    backend_name = settings.NOTIFICATION_BACKEND
    backend = _BACKENDS.get(backend_name)
    if backend is None:
        logger.warning(
            "Unknown NOTIFICATION_BACKEND %r, falling back to 'log'", backend_name
        )
        backend = _send_via_log

    recipient = customer.email

    try:
        backend(recipient, subject, content)
        status = NotificationStatus.SENT
        error = None
    except Exception as exc:
        logger.warning("Notification delivery failed", extra={"error": str(exc)})
        status = NotificationStatus.FAILED
        error = str(exc)

    notification = Notification(
        customer_id=customer_id,
        order_id=order_id,
        channel=channel,
        recipient=recipient,
        subject=subject,
        content=content,
        status=status,
        error=error
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification