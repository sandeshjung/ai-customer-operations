import time 

from fastapi import Header, HTTPException, Request

from app.core.config import settings
from app.core.redis import redis_client

def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Server misconfigured: ADMIN_API_KEY is not set."
        )
    if x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

def rate_limit(key_prefix: str, max_requests: int, window_seconds: int):
    def _dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        client_id = request.client.host if request.client else "unknown"
        window = int(time.time()) // window_seconds
        redis_key = f"ratelimit:{key_prefix}:{client_id}:{window}"

        current = redis_client.incr(redis_key)
        if current == 1:
            redis_client.expire(redis_key, window_seconds)

        if current > max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {max_requests} requests per {window_seconds}s"
            )

    return _dependency