import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.models.customer import Customer
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)

logger = get_logger(__name__)


def _send_via_log(recipient: str, subject: str | None, content: str) -> None:
    logger.info(
        "Notification (log backend - no real delivery)",
        extra={"recipient": recipient, "subject": subject, "content": content},
    )


def _send_via_mailjet(recipient: str, subject: str | None, content: str) -> None:
    """Real delivery via Mailjet's Send API v3.1. Requires MAILJET_API_KEY,
    MAILJET_API_SECRET, and MAILJET_SENDER_EMAIL (see config.py / .env.example).
    Not wired into the default flow — see the commented call site below."""
    response = httpx.post(
        "https://api.mailjet.com/v3.1/send",
        auth=(settings.MAILJET_API_KEY, settings.MAILJET_API_SECRET),
        json={
            "Messages": [
                {
                    "From": {
                        "Email": settings.MAILJET_SENDER_EMAIL,
                        "Name": settings.MAILJET_SENDER_NAME,
                    },
                    "To": [{"Email": recipient}],
                    "Subject": subject or "An update on your order",
                    "TextPart": content,
                }
            ]
        },
        timeout=10,
    )
    response.raise_for_status()


def _demo_send_via_mailjet(recipient: str, subject: str | None, content: str) -> None:
    """Best-effort wrapper around _send_via_mailjet for the demo call site in
    send_notification() — swallows and logs any failure (bad/missing
    credentials, network error, etc.) so toggling the demo on never risks
    the primary notification flow, unlike the real _BACKENDS entries above,
    which report failure back to the caller by design."""
    try:
        _send_via_mailjet(recipient, subject, content)
        logger.info("Mailjet demo send succeeded", extra={"recipient": recipient})
    except Exception as exc:  # noqa: BLE001 - demo-only real send, must never affect the primary notification flow
        logger.warning("Mailjet demo send failed", extra={"error": str(exc)})


_BACKENDS = {"log": _send_via_log}


def send_notification(
    db,
    customer_id: int,
    content: str,
    order_id: int | None = None,
    subject: str | None = None,
    channel: str = NotificationChannel.EMAIL,
) -> Notification:

    customer = db.get(Customer, customer_id)
    if customer is None:
        logger.warning(
            "Cannot notify - customer not found", extra={"customer_id": customer_id}
        )
        notification = Notification(
            customer_id=customer_id,
            order_id=order_id,
            channel=channel,
            recipient="unknown",
            subject=subject,
            content=content,
            status=NotificationStatus.FAILED,
            error="Customer not found",
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
    except Exception as exc:  # noqa: BLE001 - pluggable backend, any failure mode must be recorded, not crash the order flow
        logger.warning("Notification delivery failed", extra={"error": str(exc)})
        status = NotificationStatus.FAILED
        error = str(exc)

    # DEMO: uncomment the line below to also send a real email via Mailjet
    # (needs MAILJET_API_KEY / MAILJET_API_SECRET / MAILJET_SENDER_EMAIL in
    # .env). Runs independently of the backend above — never changes the
    # recorded status below, so the admin console keeps showing every
    # notification exactly as it does today either way.

    # _demo_send_via_mailjet(recipient, subject, content)

    notification = Notification(
        customer_id=customer_id,
        order_id=order_id,
        channel=channel,
        recipient=recipient,
        subject=subject,
        content=content,
        status=status,
        error=error,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification
