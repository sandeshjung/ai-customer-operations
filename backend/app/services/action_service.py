from sqlalchemy.orm import Session

from app.models.support_ticket import SupportTicket, TicketPriority, TicketStatus
from app.agents.models import AgentDecision, ResolutionType, DelaySeverity


def execute_decision(
    db: Session,
    order_id: int,
    customer_id: int,
    decision: AgentDecision,
) -> dict:
    actions = []

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
        actions.append("shipment_tracked")  # TODO: integrate carrier API

    elif decision.resolution == ResolutionType.CONTACT_CARRIER:
        actions.append("carrier_contacted")  # TODO: integrate carrier API

    elif decision.resolution == ResolutionType.NO_ACTION:
        actions.append("no_action_taken")

    db.commit()
    return {"actions": actions, "ticket_id": ticket.id if 'ticket' in dir() else None}