from datetime import UTC, datetime

from app.api.orders import get_order
from app.core.database import get_db
from app.core.security import rate_limit
from app.models.order import OrderStatus
from app.schemas.customer_portal import CustomerOrderLookupResponse, ShipmentInfo
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
