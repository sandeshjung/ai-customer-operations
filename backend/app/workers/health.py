import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import redis_client

logger = get_logger(__name__)

HEARTBEAT_KEY = "worker:heartbeat"


def record_heartbeat() -> None:
    try:
        redis_client.set(
            HEARTBEAT_KEY, str(time.time()), ex=settings.WORKER_HEARTBEAT_TTL_SECONDS
        )
    except Exception as exc:  # noqa: BLE001 - heartbeat failures must never propagate
        logger.warning("Failed to record worker heartbeat", extra={"error": str(exc)})


@contextmanager
def keep_alive(max_seconds: float | None = None, interval: float = 15):
    """Heartbeat from a background thread while one event is processing.

    The main loop only heartbeats between events, so a slow event (LLM
    retries, rate-limit backoff) used to let the heartbeat expire and get the
    worker restarted mid-event by autoheal. This keeps it alive — but only up
    to max_seconds, so a worker that's genuinely stuck still goes unhealthy.
    """
    limit = settings.WORKER_MAX_EVENT_SECONDS if max_seconds is None else max_seconds
    deadline = time.monotonic() + limit
    stop = threading.Event()

    def _beat():
        while not stop.wait(interval):
            if time.monotonic() > deadline:
                logger.error(
                    "Event exceeded WORKER_MAX_EVENT_SECONDS — stopping heartbeat",
                    extra={"max_seconds": limit},
                )
                return
            record_heartbeat()

    record_heartbeat()
    thread = threading.Thread(target=_beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)


def is_healthy() -> bool:
    try:
        return redis_client.exists(HEARTBEAT_KEY) > 0
    except Exception as exc:  # noqa: BLE001 - "can't reach Redis" IS unhealthy, not a crash
        logger.warning("Health check could not reach Redis", extra={"error": str(exc)})
        return False


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "not_found"}')
            return

        healthy = is_healthy()
        self.send_response(200 if healthy else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        body = '{"status": "ok"}' if healthy else '{"status": "unhealthy"}'
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        pass


def start_health_server(port: int | None = None) -> HTTPServer:
    bind_port = port if port is not None else settings.WORKER_HEALTH_PORT
    server = HTTPServer(("0.0.0.0", bind_port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Worker health server started", extra={"port": server.server_port})
    return server
