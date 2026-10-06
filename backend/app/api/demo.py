from app.core.database import get_db
from app.core.security import rate_limit, require_api_key, require_demo_enabled
from app.models.support_ticket import TicketPriority
from app.services.demo_service import (
    ShipmentScenario,
    create_customer_ticket,
    create_delayed_order,
)
from app.services.order_timeline import build_order_timeline, build_ticket_timeline
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/admin",
    tags=["Demo"],
    dependencies=[Depends(require_demo_enabled), Depends(require_api_key)],
)


class DemoDelayedOrderRequest(BaseModel):
    delay_days: int = Field(default=7, ge=1, le=60)
    shipment_scenario: ShipmentScenario = ShipmentScenario.IN_TRANSIT
    customer_id: int | None = None
    # Place the order for this customer (created if new), so its
    # notifications are addressed to an inbox you can check.
    customer_email: EmailStr | None = None


class DemoTicketRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=5000)
    priority: TicketPriority = TicketPriority.MEDIUM
    order_id: int | None = None
    # File as this customer; without order_id, uses their latest order.
    customer_email: EmailStr | None = None


@router.post(
    "/demo/delayed-order",
    # Each simulated order costs real LLM calls once the worker gets to it.
    dependencies=[
        Depends(rate_limit("demo_delayed_order", max_requests=5, window_seconds=60))
    ],
)
def create_demo_delayed_order(
    request: DemoDelayedOrderRequest, db: Session = Depends(get_db)
):
    try:
        return create_delayed_order(
            db,
            delay_days=request.delay_days,
            shipment_scenario=request.shipment_scenario,
            customer_id=request.customer_id,
            customer_email=request.customer_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/orders/{order_id}/timeline")
def get_order_timeline(
    order_id: int,
    event_id: str | None = Query(default=None),
    message_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    timeline = build_order_timeline(db, order_id, event_id, message_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return timeline


@router.post(
    "/demo/ticket",
    # Costs a real LLM call once the worker gets to it.
    dependencies=[
        Depends(rate_limit("demo_ticket", max_requests=5, window_seconds=60))
    ],
)
def create_demo_ticket(request: DemoTicketRequest, db: Session = Depends(get_db)):
    try:
        return create_customer_ticket(
            db,
            subject=request.subject,
            message=request.message,
            priority=request.priority,
            order_id=request.order_id,
            customer_email=request.customer_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/tickets/{ticket_id}/timeline")
def get_ticket_timeline(
    ticket_id: int,
    event_id: str | None = Query(default=None),
    message_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    timeline = build_ticket_timeline(db, ticket_id, event_id, message_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return timeline
