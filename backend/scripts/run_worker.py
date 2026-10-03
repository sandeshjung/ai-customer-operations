from app.core.logging import configure_logging, get_logger
from app.core.tracing import setup_tracing
from app.workers.event_consumer import consume_events
from app.workers.health import start_health_server


def warm_up_rag() -> None:
    """The embedding model and Qdrant connection load lazily on first search.
    Load them now, at start-up, so the first event doesn't pay for it."""
    from app.rag.retriever import get_vector_store

    try:
        get_vector_store()
    except Exception as exc:  # noqa: BLE001 - retried on first search anyway
        get_logger(__name__).warning("RAG warm-up failed", extra={"error": str(exc)})


if __name__ == "__main__":
    configure_logging()
    setup_tracing()
    start_health_server()
    warm_up_rag()
    consume_events()
