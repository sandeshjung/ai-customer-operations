from datetime import date, datetime
from decimal import Decimal

from app.models.order import OrderStatus
from app.models.shipment import ShipmentStatus
from app.schemas.order import OrderItemResponse
from pydantic import BaseModel


class ShipmentInfo(BaseModel):
    carrier: str
    tracking_number: str
    status: ShipmentStatus
    last_location: str | None
    last_updated: datetime


class CustomerOrderLookupResponse(BaseModel):
    order_id: int
    customer_id: int
    status: OrderStatus
    expected_delivery: date | None
    created_at: datetime
    total_amount: Decimal
    items: list[OrderItemResponse]
    is_delayed: bool
    delay_days: int | None
    shipment: ShipmentInfo | None
