import json

from app.core.redis import redis_client
from app.events.publisher import EVENT_STREAM


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
            block=1000,
        )

        if not messages:
            continue

        for _, entries in messages:
            for message_id, fields in entries:
                event = json.loads(fields["event"])

                print(
                    f"Received event "
                    f"{event['event_type']} "
                    f"({message_id})"
                )

                redis_client.xack(
                    EVENT_STREAM,
                    CONSUMER_GROUP,
                    message_id,
                )