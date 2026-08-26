from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.shipment import ShipmentStatus

class ShipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    carrier: str
    tracking_number: str 
    status: ShipmentStatus
    last_location: str | None
    last_update: datetime