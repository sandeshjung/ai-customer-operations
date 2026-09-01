from app.workers.event_consumer import consume_events
from app.core.logging import configure_logging

if __name__ == "__main__":
    configure_logging()
    consume_events()