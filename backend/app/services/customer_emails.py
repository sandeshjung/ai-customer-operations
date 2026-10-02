"""Customer-facing email content: ticket acknowledgements, order updates and
triage status updates, each with a "View status" link into the customer
portal's Track your order page.

Templated wording only — no model output goes into these except an agent's
own drafted customer_message, which was already sent to customers before.
Triage's reasoning, priority and intent are internal and never included.
"""

from dataclasses import dataclass
from html import escape

from app.agents.models import TriageAction
from app.core.config import settings
from app.models.customer import Customer
from app.services.notification_service import send_notification
from sqlalchemy.orm import Session


@dataclass
class CustomerEmail:
    subject: str
    text: str
    html: str


def order_status_url(order_id: int) -> str:
    return f"{settings.CUSTOMER_PORTAL_URL.rstrip('/')}/?order={order_id}"


def ticket_acknowledgement(
    customer_name: str | None, ticket_id: int, order_id: int, about: str
) -> CustomerEmail:
    """about: what the ticket is about, in words the customer recognises —
    their own subject line for a ticket they filed, or a plain description
    for one the delayed-order agent opened (never its internal subject)."""
    return _render(
        subject=f"We've received your request (ticket #{ticket_id})",
        customer_name=customer_name,
        paragraphs=[
            (
                f"Thanks for getting in touch. We've opened support ticket "
                f"#{ticket_id} about {about}."
            ),
            (
                "Our team is on it, and we'll email you as it progresses. You "
                "can check your order and this ticket's status at any time."
            ),
        ],
        order_id=order_id,
    )


def order_update(message: str, order_id: int, ticket_id: int | None) -> CustomerEmail:
    """The delayed-order agent's drafted customer_message. The text part stays
    exactly the message unless a ticket was opened, in which case a line
    pointing at it is appended — so one email covers both, not two."""
    paragraphs = [message]
    if ticket_id is not None:
        paragraphs.append(
            f"We've opened support ticket #{ticket_id} to follow up — you can "
            "check its status at any time."
        )
    email = _render(
        subject="An update on your order",
        customer_name=None,  # the agent's message has its own greeting
        paragraphs=paragraphs,
        order_id=order_id,
    )
    if ticket_id is None:
        email.text = message
    return email


def triage_update(
    customer_name: str | None,
    ticket_id: int,
    order_id: int | None,
    action: TriageAction,
    resolved: bool,
) -> CustomerEmail:
    """What happens next after the triage agent has looked at the ticket."""
    if resolved:
        subject = f"Your request #{ticket_id} has been resolved"
        body = (
            f"We've reviewed ticket #{ticket_id} and marked it resolved. If "
            "anything still isn't right, contact us and we'll reopen it."
        )
    elif action == TriageAction.ESCALATE:
        subject = f"Your request #{ticket_id} has been escalated"
        body = (
            f"We've reviewed ticket #{ticket_id} and passed it to a senior "
            "specialist as a priority. They'll be in touch soon."
        )
    elif action == TriageAction.AUTO_RESPOND:
        subject = f"We've reviewed your request #{ticket_id}"
        body = (
            f"We've reviewed ticket #{ticket_id}. You can follow your order's "
            "latest status below — we'll be in touch if we need anything else "
            "from you."
        )
    else:  # ROUTE_TO_AGENT, or RESOLVE that still needs a human
        subject = f"Your request #{ticket_id} is with our support team"
        body = (
            f"We've reviewed ticket #{ticket_id} and assigned it to a member "
            "of our support team, who'll reply to you personally."
        )
    return _render(
        subject=subject,
        customer_name=customer_name,
        paragraphs=[body],
        order_id=order_id,
    )


def send_customer_email(
    db: Session, customer_id: int, order_id: int | None, email: CustomerEmail
):
    return send_notification(
        db=db,
        customer_id=customer_id,
        order_id=order_id,
        subject=email.subject,
        content=email.text,
        html=email.html,
    )


def customer_first_name(db: Session, customer_id: int) -> str | None:
    customer = db.get(Customer, customer_id)
    if customer is None or not customer.name:
        return None
    return customer.name.split()[0]


def _render(
    subject: str,
    customer_name: str | None,
    paragraphs: list[str],
    order_id: int | None,
) -> CustomerEmail:
    greeting = f"Hi {customer_name}," if customer_name else None
    url = order_status_url(order_id) if order_id is not None else None

    text_parts = ([greeting] if greeting else []) + paragraphs
    if url:
        text_parts.append(f"View status: {url}")
    text_parts.append(f"— {settings.MAILJET_SENDER_NAME}")

    html_paragraphs = "".join(
        f'<p style="margin:0 0 14px;white-space:pre-wrap">{escape(p)}</p>'
        for p in ([greeting] if greeting else []) + paragraphs
    )
    button = (
        f'<p style="margin:22px 0"><a href="{escape(url)}" '
        'style="background:#2f6f78;color:#ffffff;text-decoration:none;'
        "padding:11px 20px;border-radius:5px;display:inline-block;"
        'font-weight:600">View status</a></p>'
        f'<p style="margin:0 0 14px;font-size:12px;color:#6b7280">Or open: '
        f'<a href="{escape(url)}" style="color:#2f6f78">{escape(url)}</a></p>'
        if url
        else ""
    )
    html = (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,'
        "sans-serif;font-size:15px;line-height:1.55;color:#1f2933;"
        'max-width:560px">'
        f"{html_paragraphs}{button}"
        f'<p style="margin:22px 0 0;color:#6b7280">— '
        f"{escape(settings.MAILJET_SENDER_NAME)}</p></div>"
    )
    return CustomerEmail(subject=subject, text="\n\n".join(text_parts), html=html)
