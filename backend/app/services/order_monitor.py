from datetime import date, datetime, timezone
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app.events.publisher import publish_event
from app.events.schemas import Event
from app.events.types import EventType
from app.models.order import Order
from app.core.redis import redis_client

def detect_delayed_orders(db: Session) -> int:
    today = date.today()

    delayed_orders = (
        db.query(Order)
        .filter(
            Order.expected_delivery < today,
            Order.status.notin_(
                ["DELIVERED", "CANCELLED", "REFUNDED"]
            )
        )
        .all()
    )

    published = 0

    for order in delayed_orders:

        delay_days = (
            today - order.expected_delivery
        ).days

        event_key = (
            f"delayed_order:"
            f"{order.id}:"
            f"{today.isoformat()}"
        )

        if redis_client.exists(event_key):
            continue

        event = Event(
            event_id=str(uuid4()),
            event_type=EventType.ORDER_DELAYED,
            occurred_at=datetime.now(timezone.utc),
            source="order-monitor",
            data={
                "order_id": order.id,
                "customer_id": order.customer_id,
                "expected_delivery": (
                    order.expected_delivery.isoformat()
                ),
                "delay_days": delay_days
            }
        )

        publish_event(event)

        redis_client.set(
            event_key,
            "1",
            ex=86400,
        )

        time.sleep(5)

        published += 1

    return published