from datetime import datetime

from app.models.shipment import ShipmentStatus
from pydantic import BaseModel, ConfigDict


class ShipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    carrier: str
    tracking_number: str
    status: ShipmentStatus
    last_location: str | None
    last_update: datetime
