from pydantic import BaseModel

class DelayedOrderContext(BaseModel):
    order: dict | None = None
    shipment: dict | None = None
    customer: dict | None = None

    delay_days: int

    missing_information: list[str] = []