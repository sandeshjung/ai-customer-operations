"""Recovery of events the worker didn't finish: a crash or restart (e.g. by
autoheal) mid-event used to leave the message pending forever — the loop only
ever read new (">") messages, and the 24 h idempotency claim made even a
redelivery look "already processed". Nothing reprocessed it and nothing
dead-lettered it."""

import json
import sys
import threading
import types
from contextlib import nullcontext
from unittest.mock import patch

# Same as test_consume_events.py: keep the real RAG chain out of the import.
_fake_rag_service = types.ModuleType("app.rag.service")
_fake_rag_service.retrieve_policy = lambda query, limit=5: []
sys.modules["app.rag.service"] = _fake_rag_service

import pytest
from app.events import idempotency
from app.workers import event_consumer, health


class FakeRedis:
    """Just enough Redis for claims and pending-message recovery."""

    def __init__(self, pending=(), stale=()):
        self.store = {}
        self.ttls = {}
        self.pending = list(pending)  # this consumer's unacked messages
        self.stale = list(stale)  # other consumers' idle messages
        self.acked = []
        self.xreadgroup_calls = []

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        self.ttls[key] = ex
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)

    def xreadgroup(self, groupname, consumername, streams, count=None, block=None):
        self.xreadgroup_calls.append(streams)
        assert list(streams.values()) == ["0"], "recovery must read history, not '>'"
        batch, self.pending = self.pending, []
        return [(event_consumer.EVENT_STREAM, batch)] if batch else []

    def xautoclaim(self, name, groupname, consumername, min_idle_time, **kwargs):
        claimed, self.stale = self.stale, []
        return ["0-0", claimed, []]

    def xack(self, stream, group, message_id):
        self.acked.append(message_id)


def _message(message_id, event_id):
    event = {
        "event_id": event_id,
        "event_type": "ORDER_DELAYED",
        "data": {"order_id": 1, "delay_days": 5},
        "trace_context": {},
    }
    return (message_id, {"event": json.dumps(event)})


@pytest.fixture
def fake_redis():
    redis = FakeRedis()
    with (
        patch.object(event_consumer, "redis_client", redis),
        patch.object(idempotency, "redis_client", redis),
        patch.object(event_consumer, "keep_alive", lambda: nullcontext()),
        patch("time.sleep"),
    ):
        yield redis


class TestClaims:
    def test_claim_is_short_lived_and_success_marks_done(self, fake_redis):
        assert idempotency.try_claim_event("evt-1") is True
        assert fake_redis.store["processed_event:evt-1"] == idempotency.PROCESSING
        assert fake_redis.ttls["processed_event:evt-1"] == idempotency.CLAIM_TTL_SECONDS
        assert idempotency.try_claim_event("evt-1") is False

        idempotency.mark_event_done("evt-1")

        assert idempotency.is_event_done("evt-1") is True
        assert fake_redis.ttls["processed_event:evt-1"] == idempotency.DONE_TTL_SECONDS


class TestRecoverOwnPendingMessages:
    def test_unfinished_event_from_a_previous_run_is_processed(self, fake_redis):
        fake_redis.pending = [_message("5-0", "evt-crashed")]
        # The crashed run's claim is still there — it must not block recovery.
        idempotency.try_claim_event("evt-crashed")

        with patch.object(event_consumer, "process_event") as mock_process:
            event_consumer.recover_pending_messages()

        mock_process.assert_called_once()
        assert fake_redis.acked == ["5-0"]
        assert idempotency.is_event_done("evt-crashed")

    def test_event_finished_but_not_acked_is_only_acked(self, fake_redis):
        """Crash between finishing and acking: don't run the agent twice."""
        fake_redis.pending = [_message("6-0", "evt-done")]
        idempotency.mark_event_done("evt-done")

        with patch.object(event_consumer, "process_event") as mock_process:
            event_consumer.recover_pending_messages()

        mock_process.assert_not_called()
        assert fake_redis.acked == ["6-0"]


class TestReclaimOtherConsumersStaleMessages:
    def test_long_idle_message_of_a_dead_consumer_is_taken_over(self, fake_redis):
        fake_redis.stale = [_message("7-0", "evt-orphan")]

        with patch.object(event_consumer, "process_event") as mock_process:
            event_consumer.reclaim_stale_messages()

        mock_process.assert_called_once()
        assert fake_redis.acked == ["7-0"]


class TestConsumeLoopStartsWithRecovery:
    def test_recovers_before_reading_new_messages(self, fake_redis):
        class _Stop(Exception):
            pass

        order = []

        def _read_then_stop(**kwargs):
            order.append("read")
            raise _Stop

        with (
            patch.object(event_consumer, "create_consumer_group"),
            patch.object(event_consumer, "record_heartbeat"),
            patch.object(
                event_consumer,
                "recover_pending_messages",
                side_effect=lambda: order.append("recover"),
            ),
            patch.object(
                fake_redis,
                "xreadgroup",
                side_effect=_read_then_stop,
            ),
            pytest.raises(_Stop),
        ):
            event_consumer.consume_events()

        assert order == ["recover", "read"]


class TestKeepAlive:
    """A long event used to look like a hung worker: the heartbeat was only
    written between events, so autoheal could restart the worker mid-event."""

    def test_heartbeats_while_processing(self):
        beats = []
        with (
            patch.object(health, "record_heartbeat", lambda: beats.append(1)),
            health.keep_alive(max_seconds=5, interval=0.01),
        ):
            threading.Event().wait(0.08)  # a "long" event
        assert len(beats) >= 4

    def test_stops_after_the_cap_so_a_hung_worker_still_goes_unhealthy(self):
        beats = []
        with (
            patch.object(health, "record_heartbeat", lambda: beats.append(1)),
            health.keep_alive(max_seconds=0.03, interval=0.01),
        ):
            threading.Event().wait(0.05)
            count_after_cap = len(beats)
            threading.Event().wait(0.08)
        assert len(beats) == count_after_cap
