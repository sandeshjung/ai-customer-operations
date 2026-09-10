from app.workers.event_consumer import consume_events
from app.core.logging import configure_logging
from app.core.tracing import setup_tracing

if __name__ == "__main__":
    configure_logging()
    setup_tracing()
    consume_events()