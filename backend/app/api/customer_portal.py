from datetime import UTC, datetime

from app.api.orders import get_order
from app.core.database import get_db
from app.core.security import rate_limit
from app.models.order import OrderStatus
from app.models.support_ticket import SupportTicket
from app.schemas.customer_portal import (
    CustomerOrderLookupResponse,
    CustomerTicket,
    ShipmentInfo,
)
from app.services.customer_emails import customer_ticket_title
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(prefix="/portal", tags=["Customer Portal"])

# NOTE: this is a public lookup by order number alone — no authentication and
# no second factor. There is no customer login/session system, and order IDs
# are sequential, so anyone can read any order's items, shipment and tracking
# number by trying numbers; the per-IP rate limit only slows that down. This
# is a deliberate demo-friendliness trade-off on synthetic data. A real
# deployment would need a second factor (e.g. the email on the order) or
# unguessable order references.
_NOT_FOUND_DETAIL = "We couldn't find an order with that number."


@router.get(
    "/orders/{order_id}",
    response_model=CustomerOrderLookupResponse,
    dependencies=[
        Depends(rate_limit("portal_order_lookup", max_requests=20, window_seconds=60))
    ],
)
def lookup_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    try:
        order = get_order(order_id, db)
    except HTTPException:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from None

    today = datetime.now(UTC).date()
    is_delayed = False
    delay_days = None

    if (
        order.expected_delivery
        and order.expected_delivery < today
        and order.status
        not in (OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.REFUNDED)
    ):
        is_delayed = True
        delay_days = (today - order.expected_delivery).days

    shipment = None
    if order.shipment:
        shipment = ShipmentInfo(
            carrier=order.shipment.carrier,
            tracking_number=order.shipment.tracking_number,
            status=order.shipment.status,
            last_location=order.shipment.last_location,
            last_updated=order.shipment.last_updated,
        )

    return CustomerOrderLookupResponse(
        order_id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        expected_delivery=order.expected_delivery,
        created_at=order.created_at,
        total_amount=order.total_amount,
        items=order.items,
        is_delayed=is_delayed,
        delay_days=delay_days,
        shipment=shipment,
    )


@router.get(
    "/orders/{order_id}/tickets",
    response_model=list[CustomerTicket],
    dependencies=[
        Depends(rate_limit("portal_order_lookup", max_requests=20, window_seconds=60))
    ],
)
def list_order_customer_tickets(
    order_id: int,
    db: Session = Depends(get_db),
):
    """The tickets of the customer who placed this order — same scope as the
    order lookup above, but only the fields a customer should see. Replaces
    the portal's use of GET /tickets, which returns internal fields and now
    needs the admin key."""
    try:
        order = get_order(order_id, db)
    except HTTPException:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from None

    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.customer_id == order.customer_id)
        .order_by(SupportTicket.created_at.desc())
        .all()
    )
    return [
        CustomerTicket(
            id=ticket.id,
            title=customer_ticket_title(ticket.subject, ticket.order_id),
            status=getattr(ticket.status, "value", ticket.status),
            created_at=ticket.created_at,
        )
        for ticket in tickets
    ]
