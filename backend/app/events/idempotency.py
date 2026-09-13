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


def try_claim_event(event_id: str, ttl_seconds: int = 86400) -> bool:
    return bool(
        redis_client.set(
            f"{IDEMPOTENCY_PREFIX}{event_id}",
            "1",
            nx=True,
            ex=ttl_seconds,
        )
    )


def release_event_claim(event_id: str) -> None:
    redis_client.delete(f"{IDEMPOTENCY_PREFIX}{event_id}")