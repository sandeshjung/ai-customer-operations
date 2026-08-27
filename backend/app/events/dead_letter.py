import json 

from app.core.redis import redis_client
from app.workers.config import DEAD_LETTER_STREAM

def send_to_dead_letter(event: dict, error: str) -> str:
    payload = {
        "event": json.dumps(event),
        "error": error
    }

    return redis_client.xadd(
        DEAD_LETTER_STREAM,
        payload
    )