from datetime import UTC, datetime
from uuid import uuid4

from app.agents.models import AgentDecision, DelaySeverity, ResolutionType
from app.core.logging import get_logger
from app.core.tracing import inject_trace_context
from app.events.publisher import publish_event
from app.events.schemas import Event
from app.events.types import EventType
from app.models.support_ticket import SupportTicket, TicketPriority, TicketStatus
from app.services.customer_emails import (
    customer_first_name,
    order_update,
    send_customer_email,
    ticket_acknowledgement,
)
from sqlalchemy.orm import Session

logger = get_logger(__name__)

_TRIAGE_WORTHY_RESOLUTIONS = {ResolutionType.ESCALATE, ResolutionType.CONTACT_CUSTOMER}


def execute_decision(
    db: Session,
    order_id: int,
    customer_id: int,
    decision: AgentDecision,
    task_id: str | None = None,
) -> dict:
    """task_id: the event_id of the ORDER_DELAYED that started this work.
    Forwarded on TICKET_CREATED so the triage run is attributed to the same
    task in the AI usage monitor."""
    actions = []
    ticket = None

    priority_map = {
        DelaySeverity.LOW: TicketPriority.LOW,
        DelaySeverity.MEDIUM: TicketPriority.MEDIUM,
        DelaySeverity.HIGH: TicketPriority.HIGH,
        DelaySeverity.CRITICAL: TicketPriority.CRITICAL,
    }

    if decision.resolution == ResolutionType.ESCALATE:
        ticket = SupportTicket(
            customer_id=customer_id,
            order_id=order_id,
            subject=f"ESCALATED: Delayed order ({decision.severity.value})",
            message=decision.reasoning,
            priority=priority_map.get(decision.severity, TicketPriority.HIGH),
            status=TicketStatus.OPEN,
        )
        db.add(ticket)
        actions.append("escalation_ticket_created")

    elif decision.resolution == ResolutionType.CONTACT_CUSTOMER:
        ticket = SupportTicket(
            customer_id=customer_id,
            order_id=order_id,
            subject=f"Delayed order - {decision.severity.value}",
            message=decision.customer_message or decision.reasoning,
            priority=priority_map.get(decision.severity, TicketPriority.MEDIUM),
            status=TicketStatus.OPEN,
        )
        db.add(ticket)
        actions.append("customer_contact_ticket_created")

    elif decision.resolution == ResolutionType.TRACK_SHIPMENT:
        ticket = SupportTicket(
            customer_id=customer_id,
            order_id=order_id,
            subject=f"Follow-up: track shipment ({decision.severity.value})",
            message=decision.reasoning,
            priority=priority_map.get(decision.severity, TicketPriority.LOW),
            status=TicketStatus.OPEN,
        )
        db.add(ticket)
        actions.append("shipment_tracking_ticket_created")

    elif decision.resolution == ResolutionType.CONTACT_CARRIER:
        ticket = SupportTicket(
            customer_id=customer_id,
            order_id=order_id,
            subject=f"Follow-up: contact carrier ({decision.severity.value})",
            message=decision.reasoning,
            priority=priority_map.get(decision.severity, TicketPriority.MEDIUM),
            status=TicketStatus.OPEN,
        )
        db.add(ticket)
        actions.append("carrier_contact_ticket_created")

    elif decision.resolution == ResolutionType.NO_ACTION:
        actions.append("no_action_taken")

    db.commit()

    # Refresh to get the generated ticket ID
    if ticket is not None:
        db.refresh(ticket)

        if decision.resolution in _TRIAGE_WORTHY_RESOLUTIONS:
            # Publish event so Triage Agent can pick it up. trace_context lets
            # the consumer continue this same trace instead of starting a new
            # one — call inject_trace_context() here, while the span for this
            # request/event is still the active one, not later in the consumer.
            event = Event(
                event_id=str(uuid4()),
                event_type=EventType.TICKET_CREATED,
                occurred_at=datetime.now(UTC),
                source="delayed_order_agent",
                data={
                    "ticket_id": ticket.id,
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "subject": ticket.subject,
                    "message": ticket.message,
                    "priority": ticket.priority,
                    "task_id": task_id,
                },
                trace_context=inject_trace_context(),
            )
            publish_event(event)

        logger.info(
            "Ticket created",
            extra={
                "ticket_id": ticket.id,
                "order_id": order_id,
                "resolution": decision.resolution,
                "triaged": decision.resolution in _TRIAGE_WORTHY_RESOLUTIONS,
            },
        )

    # Customer-facing tickets (the ones that go to triage) get acknowledged to
    # the customer. Internal follow-ups (track shipment, contact carrier) don't
    # — the customer never asked for anything. When the agent also drafted a
    # message, the acknowledgement rides along in that one email.
    customer_facing_ticket = (
        ticket if decision.resolution in _TRIAGE_WORTHY_RESOLUTIONS else None
    )
    email = None
    if decision.customer_message:
        email = order_update(
            decision.customer_message,
            order_id,
            customer_facing_ticket.id if customer_facing_ticket else None,
        )
    elif customer_facing_ticket is not None:
        email = ticket_acknowledgement(
            customer_first_name(db, customer_id),
            customer_facing_ticket.id,
            order_id,
            about=f"the delay on your order #{order_id}",
        )

    if email is not None:
        notification = send_customer_email(db, customer_id, order_id, email)
        actions.append(
            "customer_notified"
            if notification.status == "SENT"
            else "customer_notification_failed"
        )

    return {
        "actions": actions,
        "ticket_id": ticket.id if ticket is not None else None,
    }
