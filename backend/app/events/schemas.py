from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

class Event(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    source: str
    data: dict[str, Any] = Field(default_factory=dict)
    