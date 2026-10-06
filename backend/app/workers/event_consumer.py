import json
import time

from app.core.logging import get_logger
from app.core.redis import redis_client
from app.events.dead_letter import send_to_dead_letter
from app.events.idempotency import (
    is_event_done,
    mark_event_done,
    release_event_claim,
    take_over_claim,
    try_claim_event,
)
from app.events.publisher import EVENT_STREAM
from app.workers.config import (
    CONSUMER_GROUP,
    MAX_RETRIES,
    PENDING_RECLAIM_IDLE_MS,
    RECLAIM_INTERVAL_SECONDS,
)
from app.workers.health import keep_alive, record_heartbeat

logger = get_logger(__name__)

from app.agents.tools.order_tools import get_order
from app.core.database import SessionLocal
from app.core.tracing import extract_trace_context, traced
from app.services.agent_service import investigate_delayed_order
from app.services.approval_service import create_approval
from app.services.triage_service import process_ticket

CONSUMER_NAME = "worker-1"
# Pause after every event, as a Groq free-tier rate-limit safeguard (8K
# tokens/min for gpt-oss-120b). There used to be a second, duplicated 15 s
# sleep; one is enough now that a delayed-order run is 2-3 LLM calls and the
# LLM clients wait out a 429's retry-after themselves (LLM_MAX_RETRIES).
PROCESSING_DELAY_SECONDS = 15


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


from app.services.action_service import execute_decision


def process_event(event: dict) -> None:
    db = SessionLocal()
    logger.info(
        "Processing event",
        extra={"event_id": event["event_id"], "event_type": event["event_type"]},
    )

    try:
        with traced(
            "event.process",
            tracer_name="event_consumer",
            event_id=event["event_id"],
            event_type=event["event_type"],
            parent_context=extract_trace_context(event.get("trace_context")),
        ):
            if event["event_type"] == "ORDER_DELAYED":
                data = event["data"]
                decision = investigate_delayed_order(
                    db=db,
                    order_id=data["order_id"],
                    delay_days=data["delay_days"],
                    event_id=event["event_id"],
                )

                # Fetch customer_id from order
                order = get_order(db, data["order_id"])
                customer_id = order.get("customer_id") if order else None

                if not customer_id:
                    logger.warning(
                        "No customer_id found for order",
                        extra={"order_id": data["order_id"]},
                    )
                    return

                if decision.requires_human:
                    create_approval(
                        db=db,
                        event_id=event["event_id"],
                        order_id=data["order_id"],
                        customer_id=customer_id,
                        agent_name="delayed_order_agent",
                        decision=decision,
                    )
                    logger.info(
                        "Human approval required — action paused",
                        extra={
                            "event_id": event["event_id"],
                            "order_id": data["order_id"],
                        },
                    )
                else:
                    result = execute_decision(
                        db=db,
                        order_id=data["order_id"],
                        customer_id=customer_id,
                        decision=decision,
                        task_id=event["event_id"],
                    )
                    logger.info(
                        "Decision executed automatically",
                        extra={
                            "event_id": event["event_id"],
                            "actions": result["actions"],
                            "ticket_id": result.get("ticket_id"),
                        },
                    )

            elif event["event_type"] == "TICKET_CREATED":
                data = event["data"]
                process_ticket(
                    db=db,
                    ticket_id=data["ticket_id"],
                    event_id=event["event_id"],
                    # Set when the ticket came out of a delayed-order run;
                    # absent for customer-filed tickets, which are their own task.
                    task_id=data.get("task_id") or event["event_id"],
                )
    finally:
        db.close()

    #         if customer_id:
    #             result = execute_decision(
    #                 db=db,
    #                 order_id=data["order_id"],
    #                 customer_id=customer_id,
    #                 decision=decision,
    #             )
    #             logger.info(
    #                 "Decision executed",
    #                 extra={
    #                     "event_id": event["event_id"],
    #                     "actions": result["actions"],
    #                     "ticket_id": result.get("ticket_id"),
    #                 },
    #             )
    #         else:
    #             logger.warning(
    #                 "No customer_id found for order",
    #                 extra={"order_id": data["order_id"]},
    #             )

    #     elif event["event_type"] == "TICKET_CREATED":
    #         data = event["data"]
    #         process_ticket(
    #             db=db,
    #             ticket_id=data["ticket_id"],
    #             event_id=event["event_id"]
    #         )
    # finally:
    #     db.close()


def consume_events():
    create_consumer_group()

    print("Event consumer started...")

    # Events this consumer took but never acked — it crashed or was
    # restarted (e.g. by autoheal) mid-event. Finish them before new work.
    recover_pending_messages()
    last_reclaim = time.monotonic()

    while True:
        if time.monotonic() - last_reclaim >= RECLAIM_INTERVAL_SECONDS:
            reclaim_stale_messages()
            last_reclaim = time.monotonic()

        messages = redis_client.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=CONSUMER_NAME,
            streams={
                EVENT_STREAM: ">",
            },
            count=1,
            block=5000,
        )

        record_heartbeat()

        if not messages:
            continue

        for _, entries in messages:
            for message_id, fields in entries:
                handle_message(message_id, fields)


def recover_pending_messages() -> None:
    """Reprocess this consumer's own unacked messages from a previous run.

    Reading with ID "0" (instead of ">") returns the consumer's pending
    history. At start-up, everything pending under our name belongs to the
    previous, dead incarnation of this worker.
    """
    while True:
        batch = redis_client.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=CONSUMER_NAME,
            streams={EVENT_STREAM: "0"},
            count=100,
        )
        entries = [entry for _, stream_entries in batch for entry in stream_entries]
        # A pending entry whose stream data was trimmed comes back as None.
        entries = [(mid, fields) for mid, fields in entries if fields]
        if not entries:
            return
        logger.warning("Recovering unfinished events", extra={"count": len(entries)})
        for message_id, fields in entries:
            handle_message(message_id, fields, recovered=True)


def reclaim_stale_messages() -> None:
    """Take over messages another consumer left idle for longer than any
    event can take — that worker died. Only matters with several workers."""
    try:
        _, claimed, _ = redis_client.xautoclaim(
            EVENT_STREAM,
            CONSUMER_GROUP,
            CONSUMER_NAME,
            min_idle_time=PENDING_RECLAIM_IDLE_MS,
            start_id="0-0",
            count=10,
        )
    except Exception as exc:  # noqa: BLE001 - best effort; retried next interval
        logger.warning("Couldn't reclaim stale messages", extra={"error": str(exc)})
        return
    for message_id, fields in claimed:
        if fields:
            logger.warning(
                "Reclaimed abandoned event", extra={"message_id": message_id}
            )
            handle_message(message_id, fields, recovered=True)


def handle_message(message_id, fields: dict, recovered: bool = False) -> None:
    event = json.loads(fields["event"])

    event_id = event["event_id"]

    if recovered:
        # Its previous worker died. If it finished before dying (crash
        # between processing and acking), just ack; otherwise take over
        # the dead worker's claim and process it.
        if is_event_done(event_id):
            redis_client.xack(EVENT_STREAM, CONSUMER_GROUP, message_id)
            return
        take_over_claim(event_id)

    # Atomic claim, checked BEFORE any processing starts —
    # closes the race where two consumers (or a redelivery
    # racing a still-in-flight first attempt) could both see
    # "not yet processed" and both act on the same event.
    elif not try_claim_event(event_id):
        print(f"Skipping already claimed/processed event: {event_id}")

        redis_client.xack(
            EVENT_STREAM,
            CONSUMER_GROUP,
            message_id,
        )

        return

    success = False

    # Heartbeat while the agents run, so a slow event isn't mistaken for
    # a hung worker and restarted mid-event (see health.keep_alive).
    with keep_alive():
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"Processing attempt {attempt}/{MAX_RETRIES}: {event_id}")

                process_event(event)

                mark_event_done(event_id)

                redis_client.xack(
                    EVENT_STREAM,
                    CONSUMER_GROUP,
                    message_id,
                )

                success = True
                break

            except Exception as exc:  # noqa: BLE001 - retry/DLQ boundary must catch any failure from process_event's LLM/DB/Redis calls
                print(f"Event processing failed (attempt {attempt}): {exc}")

                if attempt < MAX_RETRIES:
                    time.sleep(2)

                else:
                    # Release the claim so a manual DLQ replay of
                    # this same event_id later isn't silently
                    # skipped as "already processed" — only a
                    # successful run should hold the claim for
                    # its full TTL.
                    release_event_claim(event_id)

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
        print(f"Event moved to DLQ: {event_id}")

    time.sleep(PROCESSING_DELAY_SECONDS)
