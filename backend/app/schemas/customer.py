from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

class CustomerCreate(BaseModel):
    name: str
    email: EmailStr

class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    created_at: datetime
