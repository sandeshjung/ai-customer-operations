import json
import sys
import types

_fake_rag_service = types.ModuleType("app.rag.service")
_fake_rag_service.retrieve_policy = lambda query, limit=5: []
sys.modules["app.rag.service"] = _fake_rag_service

from unittest.mock import call, patch 

import pytest 

from app.workers import event_consumer 
from app.workers.config import MAX_RETRIES 


class _StopLoop(Exception):
    """Sentinel used to break out of consume_events()'s `while True`."""


def _redis_batch(event: dict, message_id: str = "1-0"):
    """Shape xreadgroup's return value the way redis-py actually returns it."""
    return [("customer_operations_events", [(message_id, {"event": json.dumps(event)})])]


def _order_delayed_event(event_id: str = "evt-1") -> dict:
    return {
        "event_id": event_id,
        "event_type": "ORDER_DELAYED",
        "data": {"order_id": 1, "delay_days": 5},
        "trace_context": {},
    }


@pytest.fixture(autouse=True)
def _patch_common():
    """Every test here needs the same baseline: no real Redis group
    creation, no real sleeping, and a way to end the infinite loop."""
    with (
        patch.object(event_consumer, "create_consumer_group"),
        patch("time.sleep"),
    ):
        yield


class TestProcessesNewEvent:
    def test_acks_and_marks_processed_on_success(self):
        event = _order_delayed_event()

        with (
            patch.object(event_consumer.redis_client, "xreadgroup", side_effect=[_redis_batch(event), _StopLoop()]),
            patch.object(event_consumer.redis_client, "xack") as mock_xack,
            patch.object(event_consumer, "is_event_processed", return_value=False),
            patch.object(event_consumer, "mark_event_processed") as mock_mark,
            patch.object(event_consumer, "process_event") as mock_process,
            patch.object(event_consumer, "send_to_dead_letter") as mock_dlq,
        ):
            with pytest.raises(_StopLoop):
                event_consumer.consume_events()

        mock_process.assert_called_once_with(event)
        mock_mark.assert_called_once_with("evt-1")
        mock_xack.assert_called_once_with(
            event_consumer.EVENT_STREAM, event_consumer.CONSUMER_GROUP, "1-0"
        )
        mock_dlq.assert_not_called()


class TestSkipsAlreadyProcessed:
    def test_does_not_reprocess_but_still_acks(self):
        event = _order_delayed_event()

        with (
            patch.object(event_consumer.redis_client, "xreadgroup", side_effect=[_redis_batch(event), _StopLoop()]),
            patch.object(event_consumer.redis_client, "xack") as mock_xack,
            patch.object(event_consumer, "is_event_processed", return_value=True),
            patch.object(event_consumer, "mark_event_processed") as mock_mark,
            patch.object(event_consumer, "process_event") as mock_process,
        ):
            with pytest.raises(_StopLoop):
                event_consumer.consume_events()

        mock_process.assert_not_called()
        mock_mark.assert_not_called()
        # Still needs acking, or Redis will keep redelivering it forever.
        mock_xack.assert_called_once_with(
            event_consumer.EVENT_STREAM, event_consumer.CONSUMER_GROUP, "1-0"
        )


class TestRetryAndDeadLetter:
    def test_retries_up_to_max_then_dead_letters(self):
        event = _order_delayed_event()

        with (
            patch.object(event_consumer.redis_client, "xreadgroup", side_effect=[_redis_batch(event), _StopLoop()]),
            patch.object(event_consumer.redis_client, "xack") as mock_xack,
            patch.object(event_consumer, "is_event_processed", return_value=False),
            patch.object(event_consumer, "mark_event_processed") as mock_mark,
            patch.object(event_consumer, "process_event", side_effect=RuntimeError("boom")) as mock_process,
            patch.object(event_consumer, "send_to_dead_letter") as mock_dlq,
        ):
            with pytest.raises(_StopLoop):
                event_consumer.consume_events()

        assert mock_process.call_count == MAX_RETRIES
        mock_dlq.assert_called_once_with(event, "boom")
        mock_mark.assert_not_called()
        # DLQ'd events still get acked so they're removed from the pending
        # entries list — otherwise they'd sit unacked forever.
        mock_xack.assert_called_once_with(
            event_consumer.EVENT_STREAM, event_consumer.CONSUMER_GROUP, "1-0"
        )

    def test_recovers_within_retry_budget(self):
        """Fails once, succeeds on the second attempt — should NOT reach
        the dead letter queue."""
        event = _order_delayed_event()

        with (
            patch.object(event_consumer.redis_client, "xreadgroup", side_effect=[_redis_batch(event), _StopLoop()]),
            patch.object(event_consumer.redis_client, "xack") as mock_xack,
            patch.object(event_consumer, "is_event_processed", return_value=False),
            patch.object(event_consumer, "mark_event_processed") as mock_mark,
            patch.object(
                event_consumer, "process_event", side_effect=[RuntimeError("transient"), None]
            ) as mock_process,
            patch.object(event_consumer, "send_to_dead_letter") as mock_dlq,
        ):
            with pytest.raises(_StopLoop):
                event_consumer.consume_events()

        assert mock_process.call_count == 2
        mock_mark.assert_called_once_with("evt-1")
        mock_dlq.assert_not_called()
        mock_xack.assert_called_once()


class TestSleepBehavior:
    def test_sleeps_twice_per_message_regardless_of_outcome(self):
        event = _order_delayed_event()

        with (
            patch.object(event_consumer.redis_client, "xreadgroup", side_effect=[_redis_batch(event), _StopLoop()]),
            patch.object(event_consumer.redis_client, "xack"),
            patch.object(event_consumer, "is_event_processed", return_value=False),
            patch.object(event_consumer, "mark_event_processed"),
            patch.object(event_consumer, "process_event"),
            patch("time.sleep") as mock_sleep,
        ):
            with pytest.raises(_StopLoop):
                event_consumer.consume_events()

        assert mock_sleep.call_args_list == [call(15), call(15)]