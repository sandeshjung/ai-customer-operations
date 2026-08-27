from datetime import datetime, timezone
from uuid import uuid4

from app.events.publisher import publish_event
from app.events.schemas import Event
from app.events.types import EventType

event = Event(
    event_id=str(uuid4()),
    event_type=EventType.ORDER_CREATED,
    occurred_at=datetime.now(timezone.utc),
    source="test-script",
    data={
        "order_id": 123,
        "customer_id": 456,
    }
)

message_id = publish_event(event)

print(f"Published event: {message_id}")