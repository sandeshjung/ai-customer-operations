import json
import sys
import types

# Same reasoning as test_event_consumer.py: importing event_consumer
# transitively imports the real RAG/embedding chain unless this is
# stubbed first, before any test-level fixture gets a chance to run.
_fake_rag_service = types.ModuleType("app.rag.service")
_fake_rag_service.retrieve_policy = lambda query, limit=5: []
sys.modules["app.rag.service"] = _fake_rag_service

from contextlib import nullcontext
from unittest.mock import call, patch

import pytest
from app.workers import event_consumer
from app.workers.config import MAX_RETRIES


class _StopLoop(Exception):
    """Sentinel used to break out of consume_events()'s `while True`."""


def _redis_batch(event: dict, message_id: str = "1-0"):
    """Shape xreadgroup's return value the way redis-py actually returns it."""
    return [
        ("customer_operations_events", [(message_id, {"event": json.dumps(event)})])
    ]


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
    creation, no real sleeping, no real heartbeat writes, and a way to
    end the infinite loop."""
    with (
        patch.object(event_consumer, "create_consumer_group"),
        patch.object(event_consumer, "record_heartbeat"),
        # Start-up recovery and stale-message reclaiming have their own tests
        # (test_event_recovery.py); here they'd consume the scripted reads.
        patch.object(event_consumer, "recover_pending_messages"),
        patch.object(event_consumer, "reclaim_stale_messages"),
        patch.object(event_consumer, "mark_event_done"),
        patch.object(event_consumer, "keep_alive", lambda: nullcontext()),
        patch("time.sleep"),
    ):
        yield


class TestProcessesNewEvent:
    def test_claims_processes_and_acks_on_success(self):
        event = _order_delayed_event()

        with (
            patch.object(
                event_consumer.redis_client,
                "xreadgroup",
                side_effect=[_redis_batch(event), _StopLoop()],
            ),
            patch.object(event_consumer.redis_client, "xack") as mock_xack,
            patch.object(
                event_consumer, "try_claim_event", return_value=True
            ) as mock_claim,
            patch.object(event_consumer, "release_event_claim") as mock_release,
            patch.object(event_consumer, "process_event") as mock_process,
            patch.object(event_consumer, "send_to_dead_letter") as mock_dlq,
            pytest.raises(_StopLoop),
        ):
            event_consumer.consume_events()

        mock_claim.assert_called_once_with("evt-1")
        mock_process.assert_called_once_with(event)
        mock_xack.assert_called_once_with(
            event_consumer.EVENT_STREAM, event_consumer.CONSUMER_GROUP, "1-0"
        )
        mock_dlq.assert_not_called()
        # A successful run keeps its claim for the full TTL — releasing
        # it would let the same event be reprocessed as if new.
        mock_release.assert_not_called()


class TestSkipsAlreadyClaimed:
    def test_does_not_reprocess_but_still_acks(self):
        """try_claim_event() returning False covers both "another
        consumer is processing this right now" and "this already
        completed successfully" — either way, this delivery should back
        off rather than reprocess."""
        event = _order_delayed_event()

        with (
            patch.object(
                event_consumer.redis_client,
                "xreadgroup",
                side_effect=[_redis_batch(event), _StopLoop()],
            ),
            patch.object(event_consumer.redis_client, "xack") as mock_xack,
            patch.object(event_consumer, "try_claim_event", return_value=False),
            patch.object(event_consumer, "process_event") as mock_process,
            pytest.raises(_StopLoop),
        ):
            event_consumer.consume_events()

        mock_process.assert_not_called()
        # Still needs acking, or Redis will keep redelivering it forever.
        mock_xack.assert_called_once_with(
            event_consumer.EVENT_STREAM, event_consumer.CONSUMER_GROUP, "1-0"
        )


class TestRetryAndDeadLetter:
    def test_retries_up_to_max_then_dead_letters_and_releases_claim(self):
        event = _order_delayed_event()

        with (
            patch.object(
                event_consumer.redis_client,
                "xreadgroup",
                side_effect=[_redis_batch(event), _StopLoop()],
            ),
            patch.object(event_consumer.redis_client, "xack") as mock_xack,
            patch.object(event_consumer, "try_claim_event", return_value=True),
            patch.object(event_consumer, "release_event_claim") as mock_release,
            patch.object(
                event_consumer, "process_event", side_effect=RuntimeError("boom")
            ) as mock_process,
            patch.object(event_consumer, "send_to_dead_letter") as mock_dlq,
            pytest.raises(_StopLoop),
        ):
            event_consumer.consume_events()

        assert mock_process.call_count == MAX_RETRIES
        mock_dlq.assert_called_once_with(event, "boom")
        # Releasing the claim on final failure means a manual DLQ replay
        # of this event_id later won't be silently skipped as a dup.
        mock_release.assert_called_once_with("evt-1")
        # DLQ'd events still get acked so they're removed from the pending
        # entries list — otherwise they'd sit unacked forever.
        mock_xack.assert_called_once_with(
            event_consumer.EVENT_STREAM, event_consumer.CONSUMER_GROUP, "1-0"
        )

    def test_recovers_within_retry_budget_without_releasing_claim(self):
        """Fails once, succeeds on the second attempt — should NOT reach
        the dead letter queue, and should NOT release its claim (it
        succeeded; the claim should stick for its full TTL)."""
        event = _order_delayed_event()

        with (
            patch.object(
                event_consumer.redis_client,
                "xreadgroup",
                side_effect=[_redis_batch(event), _StopLoop()],
            ),
            patch.object(event_consumer.redis_client, "xack") as mock_xack,
            patch.object(event_consumer, "try_claim_event", return_value=True),
            patch.object(event_consumer, "release_event_claim") as mock_release,
            patch.object(
                event_consumer,
                "process_event",
                side_effect=[RuntimeError("transient"), None],
            ) as mock_process,
            patch.object(event_consumer, "send_to_dead_letter") as mock_dlq,
            pytest.raises(_StopLoop),
        ):
            event_consumer.consume_events()

        assert mock_process.call_count == 2
        mock_dlq.assert_not_called()
        mock_release.assert_not_called()
        mock_xack.assert_called_once()


class TestSleepBehavior:
    """consume_events() pauses PROCESSING_DELAY_SECONDS once per message,
    whatever the outcome, as a Groq free-tier rate-limit safeguard.

    It used to sleep twice (a hardcoded 15 s plus PROCESSING_DELAY_SECONDS),
    30 s of dead time that capped the worker at ~2 events/minute. That was a
    duplicated safeguard; it was halved deliberately once a delayed-order run
    dropped to 2-3 LLM calls and the LLM clients started waiting out 429s.
    """

    def test_sleeps_once_per_message_regardless_of_outcome(self):
        event = _order_delayed_event()

        with (
            patch.object(
                event_consumer.redis_client,
                "xreadgroup",
                side_effect=[_redis_batch(event), _StopLoop()],
            ),
            patch.object(event_consumer.redis_client, "xack"),
            patch.object(event_consumer, "try_claim_event", return_value=True),
            patch.object(event_consumer, "process_event"),
            patch("time.sleep") as mock_sleep,
            pytest.raises(_StopLoop),
        ):
            event_consumer.consume_events()

        assert mock_sleep.call_args_list == [
            call(event_consumer.PROCESSING_DELAY_SECONDS)
        ]
