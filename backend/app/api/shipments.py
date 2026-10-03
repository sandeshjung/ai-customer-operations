from datetime import UTC, datetime

from app.core.database import get_db
from app.core.security import require_api_key
from app.models.order import Order, OrderStatus
from app.models.shipment import Shipment, ShipmentStatus
from app.schemas.shipment import ShipmentResponse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(prefix="/shipments", tags=["Shipments"])


@router.post(
    "/{order_id}",
    response_model=ShipmentResponse,
    dependencies=[Depends(require_api_key)],
)
def create_shipment(
    order_id: int,
    carrier: str,
    tracking_number: str,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    if order.shipment:
        raise HTTPException(
            status_code=400,
            detail="Shipment already exists for this order",
        )

    if db.query(Shipment).filter(Shipment.tracking_number == tracking_number).first():
        raise HTTPException(
            status_code=400,
            detail="Tracking number already in use",
        )

    shipment = Shipment(
        order_id=order_id,
        carrier=carrier,
        tracking_number=tracking_number,
        status=ShipmentStatus.LABEL_CREATED,
        last_location="Warehouse",
        last_updated=datetime.now(UTC),
    )

    db.add(shipment)

    order.status = OrderStatus.SHIPPED

    db.commit()
    db.refresh(shipment)

    return shipment
