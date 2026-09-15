from app.core.logging import configure_logging
from app.core.tracing import setup_tracing
from app.workers.event_consumer import consume_events
from app.workers.health import start_health_server

if __name__ == "__main__":
    configure_logging()
    setup_tracing()
    start_health_server()
    consume_events()