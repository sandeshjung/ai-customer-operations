import time
from datetime import UTC, datetime
from uuid import uuid4

from app.core.redis import redis_client
from app.events.publisher import publish_event
from app.events.schemas import Event
from app.events.types import EventType
from app.models.order import Order
from sqlalchemy.orm import Session


def detect_delayed_orders(db: Session, limit: int | None = None) -> int:
    today = datetime.now(UTC).date()

    delayed_orders = (
        db.query(Order)
        .filter(
            Order.expected_delivery < today,
            Order.status.notin_(["DELIVERED", "CANCELLED", "REFUNDED"]),
        )
        .all()
    )

    published = 0

    for order in delayed_orders:
        delay_days = (today - order.expected_delivery).days

        event_key = f"delayed_order:{order.id}:{today.isoformat()}"

        if redis_client.exists(event_key):
            continue

        event = Event(
            event_id=str(uuid4()),
            event_type=EventType.ORDER_DELAYED,
            occurred_at=datetime.now(UTC),
            source="order-monitor",
            data={
                "order_id": order.id,
                "customer_id": order.customer_id,
                "expected_delivery": (order.expected_delivery.isoformat()),
                "delay_days": delay_days,
            },
        )

        publish_event(event)

        redis_client.set(
            event_key,
            "1",
            ex=86400,
        )

        time.sleep(5)

        published += 1

        if limit is not None and published >= limit:
            break

    return published
