from datetime import date

from pydantic import BaseModel


class DelayedOrderResponse(BaseModel):
    order_id: int
    customer_id: int
    expected_delivery: date
    delay_days: int
    shipment_status: str | None
    tracking_number: str | None
