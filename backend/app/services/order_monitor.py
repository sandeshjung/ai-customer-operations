from datetime import UTC, date, datetime
from uuid import uuid4

from app.core.redis import redis_client
from app.events.publisher import publish_event
from app.events.schemas import Event
from app.events.types import EventType
from app.models.order import Order
from sqlalchemy.orm import Session


def delayed_order_dedupe_key(order_id: int, day: date) -> str:
    """Redis key marking that ORDER_DELAYED was already published for this
    order today — shared with the demo simulator so it can't double-publish."""
    return f"delayed_order:{order_id}:{day.isoformat()}"


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
        if limit is not None and published >= limit:
            break

        delay_days = (today - order.expected_delivery).days

        # Claim today's publish slot atomically *before* publishing (SET NX),
        # so two overlapping monitor runs can't both publish the same order —
        # a plain exists-then-set check let both through.
        event_key = delayed_order_dedupe_key(order.id, today)
        if not redis_client.set(event_key, "1", nx=True, ex=86400):
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

        try:
            publish_event(event)
        except Exception:
            # Give the slot back so a later run can publish this order.
            redis_client.delete(event_key)
            raise

        # No sleep between publishes: this runs inside an HTTP request, and
        # pacing here never protected anything — the worker already takes
        # events one at a time with its own delay (CLAUDE.md gotcha #3).
        published += 1

    return published
