from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.order import Order
from app.models.shipment import Shipment, ShipmentStatus
from app.schemas.shipment import ShipmentResponse

router = APIRouter(
    prefix="/shipments",
    tags=["Shipments"]
)

@router.post(
    "/{order_id}",
    response_model=ShipmentResponse,
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

    shipment = Shipment(
        order_id=order_id,
        carrier=carrier,
        tracking_number=tracking_number,
        status=ShipmentStatus.LABEL_CREATED,
        last_location="Warehouse",
        last_update=datetime.utcnow(),
    )

    db.add(shipment)

    order.status = "Shipped"

    db.commit()
    db.refresh(shipment)

    return shipment