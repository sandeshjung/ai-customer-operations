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

from app.services.agent_service import investigate_delayed_order

CONSUMER_GROUP = "customer_operations_workers"
CONSUMER_NAME = "worker-1"


def create_consumer_group():
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


def process_event(event: dict) -> None:
   
    logger.info(
        "Processing event",
        extra={
            "event_id": event["event_id"],
            "event_type": event["event_type"],
        },
    )

    if event["event_type"] == "ORDER_DELAYED":

        data = event["data"]
        decision = investigate_delayed_order(
            order_id=data["order_id"],
            delay_days=data["delay_days"],
            event_id=event["event_id"]
        )   

        print("Agent decision:")

        print(decision.model_dump_json(indent=2))


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
            count=10,
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

                if not success:
                    print(
                        f"Event moved to DLQ: "
                        f"{event_id}"
                    )