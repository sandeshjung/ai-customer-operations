from typing import Any

from app.core.database import get_db
from app.models.support_ticket import SupportTicket, TicketStatus
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _value_of(value):
    return value.value if hasattr(value, "value") else value


@router.get("")
def list_tickets(
    status: str | None = Query(default=None, alias="status"),
    customer_id: int | None = Query(default=None, alias="customer_id"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = db.query(SupportTicket).options(selectinload(SupportTicket.customer))

    if customer_id is not None:
        query = query.filter(SupportTicket.customer_id == customer_id)

    if status:
        normalized = status.strip().upper()
        try:
            ticket_status = TicketStatus(normalized)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status value: {status}",
            ) from exc
        query = query.filter(SupportTicket.status == ticket_status)

    tickets = query.order_by(SupportTicket.created_at.desc()).all()

    return [
        {
            "id": ticket.id,
            "customer_id": ticket.customer_id,
            "customer_email": ticket.customer.email,
            "order_id": ticket.order_id,
            "subject": ticket.subject,
            "message": ticket.message,
            "priority": _value_of(ticket.priority),
            "status": _value_of(ticket.status),
            "created_at": ticket.created_at,
        }
        for ticket in tickets
    ]
