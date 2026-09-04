from app.core.database import SessionLocal
from app.models.support_ticket import SupportTicket
from app.models.customer import Customer
from app.models.order import Order

def get_ticket(db, ticket_id: int) -> dict:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        return {
            "error": "Ticket not found."
        }
    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "message": ticket.message,
        "priority": ticket.priority,
        "status": ticket.status,
        "customer_id": ticket.customer_id,
        "order_id": ticket.order_id
    }

def get_customer_tickets(db, customer_id: int, limit: int = 5) -> list[dict]:
    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.customer_id == customer_id)
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": t.id,
            "subject": t.subject,
            "priority": t.priority,
            "status": t.status,
            "created_at": t.created_at.isoformat()
        }
        for t in tickets
    ]