from app.core.redis import redis_client

IDEMPOTENCY_PREFIX = "processed_event:"

def is_event_processed(event_id: str) -> bool:
    return bool(
        redis_client.exists(
            f"{IDEMPOTENCY_PREFIX}{event_id}"
        )
    )

def mark_event_processed(
    event_id: str,
    ttl_seconds: int = 86400,
) -> None:
    redis_client.set(
        f"{IDEMPOTENCY_PREFIX}{event_id}",
        "1",
        ex=ttl_seconds
    )