from decimal import Decimal

from pydantic import BaseModel, ConfigDict

class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    price: Decimal

class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price: Decimal