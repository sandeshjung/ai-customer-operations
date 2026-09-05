import json
import time

from app.core.redis import redis_client
from app.events.dead_letter import send_to_dead_letter
from app.events.idempotency import (
    is_event_processed,
    mark_event_processed,
)
from app.events.publisher import EVENT_STREAM
from app.workers.config import MAX_RETRIES

from app.core.logging import get_logger

logger = get_logger(__name__)

from app.core.database import SessionLocal
from app.agents.tools.order_tools import get_order


from app.services.agent_service import investigate_delayed_order
from app.services.triage_service import process_ticket

CONSUMER_GROUP = "customer_operations_workers"
CONSUMER_NAME = "worker-1"
PROCESSING_DELAY_SECONDS = 15


def create_consumer_group():
    db = SessionLocal()
    try:
        redis_client.xgroup_create(
            EVENT_STREAM,
            CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


from app.services.action_service import execute_decision
from app.agents.tools.order_tools import get_order  # or your order service

def process_event(event: dict) -> None:
    db = SessionLocal()
    logger.info("Processing event", extra={"event_id": event["event_id"], "event_type": event["event_type"]})

    try:
        if event["event_type"] == "ORDER_DELAYED":
            data = event["data"]
            decision = investigate_delayed_order(
                db=db,
                order_id=data["order_id"],
                delay_days=data["delay_days"],
                event_id=event["event_id"]
            )

            # Fetch customer_id from order
            order = get_order(db, data["order_id"])
            customer_id = order.get("customer_id") if order else None

            if customer_id:
                result = execute_decision(
                    db=db,
                    order_id=data["order_id"],
                    customer_id=customer_id,
                    decision=decision,
                )
                logger.info(
                    "Decision executed",
                    extra={
                        "event_id": event["event_id"],
                        "actions": result["actions"],
                        "ticket_id": result.get("ticket_id"),
                    },
                )
            else:
                logger.warning(
                    "No customer_id found for order",
                    extra={"order_id": data["order_id"]},
                )

        elif event["event_type"] == "TICKET_CREATED":
            data = event["data"]
            process_ticket(
                db=db,
                ticket_id=data["ticket_id"],
                event_id=event["event_id"]
            )
    finally:
        db.close()

def consume_events():
    create_consumer_group()

    print("Event consumer started...")

    while True:
        messages = redis_client.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=CONSUMER_NAME,
            streams={
                EVENT_STREAM: ">",
            },
            count=1,
            block=5000,
        )

        if not messages:
            continue

        for _, entries in messages:
            for message_id, fields in entries:
                event = json.loads(fields["event"])

                event_id = event["event_id"]

                if is_event_processed(event_id):
                    print(
                        f"Skipping already processed event: "
                        f"{event_id}"
                    )

                    redis_client.xack(
                        EVENT_STREAM,
                        CONSUMER_GROUP,
                        message_id,
                    )

                    continue

                success = False

                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        print(
                            f"Processing attempt "
                            f"{attempt}/{MAX_RETRIES}: "
                            f"{event_id}"
                        )

                        process_event(event)

                        mark_event_processed(event_id)

                        redis_client.xack(
                            EVENT_STREAM,
                            CONSUMER_GROUP,
                            message_id,
                        )

                        success = True
                        break

                    except Exception as exc:
                        print(
                            f"Event processing failed "
                            f"(attempt {attempt}): {exc}"
                        )

                        if attempt < MAX_RETRIES:
                            time.sleep(2)

                        else:
                            send_to_dead_letter(
                                event,
                                str(exc),
                            )

                            redis_client.xack(
                                EVENT_STREAM,
                                CONSUMER_GROUP,
                                message_id,
                            )
                time.sleep(15)

                if not success:
                    print(
                        f"Event moved to DLQ: "
                        f"{event_id}"
                    )

                time.sleep(PROCESSING_DELAY_SECONDS)