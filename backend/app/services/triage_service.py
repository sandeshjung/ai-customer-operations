from app.agents.graphs.triage_agent import triage_graph
from app.agents.models import TriageAction, TicketPriority, TicketStatus
from app.models.support_ticket import SupportTicket
from app.core.logging import get_logger

logger = get_logger(__name__)

def process_ticket(db, ticket_id: int, event_id: str):
    from app.agents.tools.ticket_tools import get_ticket, get_customer_tickets
    from app.rag.service import retrieve_policy

    ticket = get_ticket(db, ticket_id)
    if "error" in ticket:
        logger.warning("Ticket not found for triage", extra={"ticket_id": ticket_id})
        return

    # Retrieve customer history
    history = get_customer_tickets(db, ticket["customer_id"], limit=5)

    # Retrieve relevant policy
    policy_query = f"{ticket['subject']} {ticket['message']}"[:200]
    policy_results = retrieve_policy(policy_query, limit=3)
    policy_context = "\n\n".join([r["content"] for r in policy_results])

    # Run triage agent
    result = triage_graph.invoke({
        "ticket_id": ticket_id,
        "ticket": ticket,
        "customer_history": history,
        "policy_context": policy_context
    })

    decision = result["decision"]

    # update ticket based on triage
    db_ticket = db.get(SupportTicket, ticket_id)

    if db_ticket:
        # update priority if triage says higher 
        priority_map = {
            "LOW": TicketPriority.LOW,
            "MEDIUM": TicketPriority.MEDIUM,
            "HIGH": TicketPriority.HIGH,
            "CRITICAL": TicketPriority.CRITICAL,
        }
        triage_priority = priority_map.get(decision.priority)
        if triage_priority and triage_priority.value > db_ticket.priority.value:
            db_ticket.priority = triage_priority.value

        # Auto resolve simple cases
        if decision.action == TriageAction.RESOLVE and not decision.requires_human:
            db_ticket.status = TicketStatus.RESOLVED

        db.commit()

    logger.info(
        "Ticket triage completed",
        extra={
            "ticket_id": ticket_id,
            "event_id": event_id,
            "intent": decision.intent,
            "priority": decision.priority,
            "action": decision.action
        }
    )

    return decision