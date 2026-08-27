import json

from app.core.redis import redis_client
from app.events.schemas import Event

EVENT_STREAM = "customer_operations_events"

def publish_event(event: Event) -> str:
    message_id = redis_client.xadd(
        EVENT_STREAM,
        {
            "event": json.dumps(
                event.model_dump(mode="json")
            )
        }
    )

    return message_id