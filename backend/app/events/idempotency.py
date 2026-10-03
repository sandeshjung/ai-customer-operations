"""Per-event claims, so an event is processed once even across redeliveries.

A claim has two states:
- PROCESSING (short TTL) while a worker is working on the event. If that
  worker dies, the claim expires on its own — and a recovering worker may
  take it over (see event_consumer.recover_pending_messages).
- DONE (24 h) once the event was processed successfully, so a redelivery of
  a finished event is acked without running the agents again.
"""

from app.core.logging import get_logger
from app.core.redis import redis_client

logger = get_logger(__name__)

IDEMPOTENCY_PREFIX = "processed_event:"

PROCESSING = "processing"
DONE = "done"

# Must outlive the longest event (WORKER_MAX_EVENT_SECONDS, 15 min).
CLAIM_TTL_SECONDS = 20 * 60
DONE_TTL_SECONDS = 24 * 60 * 60


def _key(event_id: str) -> str:
    return f"{IDEMPOTENCY_PREFIX}{event_id}"


def try_claim_event(event_id: str, ttl_seconds: int = CLAIM_TTL_SECONDS) -> bool:
    """Atomic (SET NX): only one caller can claim an unclaimed event."""
    return bool(redis_client.set(_key(event_id), PROCESSING, nx=True, ex=ttl_seconds))


def take_over_claim(event_id: str) -> None:
    """Claim an event whose previous worker died mid-processing. Only for
    recovered messages, which by definition nobody else is working on."""
    redis_client.set(_key(event_id), PROCESSING, ex=CLAIM_TTL_SECONDS)


def is_event_done(event_id: str) -> bool:
    return redis_client.get(_key(event_id)) == DONE


def mark_event_done(event_id: str) -> None:
    # Never fail an event that already succeeded over this: worst case the
    # PROCESSING claim just expires, and the message is acked either way.
    try:
        redis_client.set(_key(event_id), DONE, ex=DONE_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - bookkeeping only
        logger.warning(
            "Couldn't mark event done", extra={"event_id": event_id, "error": str(exc)}
        )


def release_event_claim(event_id: str) -> None:
    redis_client.delete(_key(event_id))
