from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

class Event(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    source: str
    data: dict[str, Any] = Field(default_factory=dict)
    trace_context: dict[str, str] = Field(
        default_factory=dict,
        description="W3C traceparent carrier, set via inject_trace_context() at "
        "publish time, so the consuming span can continue the same trace "
        "instead of starting a new one.",
    )