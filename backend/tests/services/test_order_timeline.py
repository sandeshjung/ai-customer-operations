from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from app.models.agent_execution import AgentExecution
from app.models.customer import Customer
from app.models.human_approval import HumanApproval
from app.models.order import Order, OrderStatus
from app.models.support_ticket import SupportTicket
from app.services import order_timeline
from app.services.order_timeline import build_order_timeline


@pytest.fixture
def redis_state():
    """Controls what the timeline sees in Redis: queue position + DLQ."""
    state = {"queue": None, "dead_letters": {}}
    with (
        patch.object(
            order_timeline, "_queue_position", side_effect=lambda _: state["queue"]
        ),
        patch.object(
            order_timeline,
            "_dead_letters_for",
            side_effect=lambda *_: state["dead_letters"],
        ),
    ):
        yield state


def _make_order(db_session) -> Order:
    customer = Customer(name="T", email=f"t-{uuid4().hex[:8]}@example.com")
    db_session.add(customer)
    db_session.commit()
    order = Order(
        customer_id=customer.id,
        total_amount=10,
        expected_delivery=datetime.now(UTC).date() - timedelta(days=5),
        status=OrderStatus.SHIPPED,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def _make_run(db_session, order, agent_name="delayed_order_agent", **decision):
    execution = AgentExecution(
        agent_name=agent_name,
        event_id="evt-1" if agent_name == "delayed_order_agent" else "evt-2",
        order_id=order.id,
        input_data={"order_id": order.id},
        decision={"severity": "LOW", "resolution": "TRACK_SHIPMENT", **decision},
        steps=[{"tool": "get_order", "args": {"order_id": order.id}, "result": "{}"}],
    )
    db_session.add(execution)
    db_session.commit()
    return execution


def _make_approval(db_session, order, status="PENDING"):
    approval = HumanApproval(
        event_id="evt-1",
        order_id=order.id,
        customer_id=order.customer_id,
        agent_name="delayed_order_agent",
        decision={},
        status=status,
    )
    db_session.add(approval)
    db_session.commit()
    return approval


def _make_ticket(db_session, order) -> SupportTicket:
    ticket = SupportTicket(
        customer_id=order.customer_id,
        order_id=order.id,
        subject="ESCALATED",
        message="m",
        priority="HIGH",
        status="OPEN",
    )
    db_session.add(ticket)
    db_session.commit()
    return ticket


def _stages(timeline) -> dict:
    return {s["key"]: s for s in timeline["stages"]}


def test_returns_none_for_unknown_order(db_session, redis_state):
    assert build_order_timeline(db_session, 999) is None


def test_queued_event_reports_queue_position(db_session, redis_state):
    order = _make_order(db_session)
    redis_state["queue"] = {"picked_up": False, "ahead": 3}

    timeline = build_order_timeline(db_session, order.id, "evt-1", "5-0")

    stages = _stages(timeline)
    assert timeline["state"] == "in_progress"
    assert stages["event_queued"]["status"] == "active"
    assert stages["event_queued"]["detail"]["queue"]["ahead"] == 3
    assert stages["delay_agent"]["status"] == "pending"


def test_picked_up_event_shows_agent_running(db_session, redis_state):
    order = _make_order(db_session)
    redis_state["queue"] = {"picked_up": True, "ahead": 0}

    stages = _stages(build_order_timeline(db_session, order.id, "evt-1", "5-0"))

    assert stages["event_queued"]["status"] == "done"
    assert stages["delay_agent"]["status"] == "active"


def test_dead_lettered_event_fails_the_timeline(db_session, redis_state):
    order = _make_order(db_session)
    redis_state["dead_letters"] = {"ORDER_DELAYED": "LLM returned invalid JSON"}

    timeline = build_order_timeline(db_session, order.id, "evt-1")

    assert timeline["state"] == "failed"
    assert _stages(timeline)["delay_agent"]["detail"]["error"] == (
        "LLM returned invalid JSON"
    )


def test_auto_executed_non_triage_resolution_completes(db_session, redis_state):
    order = _make_order(db_session)
    _make_run(db_session, order, resolution="TRACK_SHIPMENT")

    timeline = build_order_timeline(db_session, order.id)

    stages = _stages(timeline)
    assert timeline["state"] == "complete"
    assert stages["delay_agent"]["detail"]["steps"][0]["tool"] == "get_order"
    assert stages["human_review"]["status"] == "skipped"
    assert stages["actions"]["status"] == "done"
    assert stages["triage"]["status"] == "skipped"


def test_pending_approval_awaits_human(db_session, redis_state):
    order = _make_order(db_session)
    _make_run(db_session, order, resolution="ESCALATE", requires_human=True)
    approval = _make_approval(db_session, order)

    timeline = build_order_timeline(db_session, order.id)

    stages = _stages(timeline)
    assert timeline["state"] == "awaiting_approval"
    assert stages["human_review"]["status"] == "active"
    assert stages["human_review"]["detail"]["approval_id"] == approval.id
    assert "actions" not in stages


def test_rejected_approval_skips_actions(db_session, redis_state):
    order = _make_order(db_session)
    _make_run(db_session, order, resolution="ESCALATE", requires_human=True)
    _make_approval(db_session, order, status="REJECTED")

    timeline = build_order_timeline(db_session, order.id)

    stages = _stages(timeline)
    assert timeline["state"] == "complete"
    assert stages["human_review"]["detail"]["outcome"] == "REJECTED"
    assert stages["actions"]["status"] == "skipped"


def test_approved_escalation_waits_for_triage(db_session, redis_state):
    order = _make_order(db_session)
    _make_run(db_session, order, resolution="ESCALATE", requires_human=True)
    _make_approval(db_session, order, status="APPROVED")
    _make_ticket(db_session, order)

    timeline = build_order_timeline(db_session, order.id)

    stages = _stages(timeline)
    assert timeline["state"] == "in_progress"
    assert len(stages["actions"]["detail"]["tickets"]) == 1
    assert stages["triage"]["status"] == "active"


def test_triage_run_completes_timeline(db_session, redis_state):
    order = _make_order(db_session)
    _make_run(db_session, order, resolution="CONTACT_CUSTOMER")
    ticket = _make_ticket(db_session, order)
    triage = AgentExecution(
        agent_name="triage_agent",
        event_id="evt-2",
        order_id=order.id,
        input_data={"ticket_id": ticket.id},
        decision={"intent": "DELIVERY_DELAY", "priority": "HIGH"},
    )
    db_session.add(triage)
    db_session.commit()

    timeline = build_order_timeline(db_session, order.id)

    stages = _stages(timeline)
    assert timeline["state"] == "complete"
    assert stages["triage"]["status"] == "done"
    assert stages["triage"]["detail"]["decision"]["intent"] == "DELIVERY_DELAY"
    assert stages["triage"]["detail"]["ticket"]["id"] == ticket.id


def test_dead_lettered_ticket_event_fails_triage(db_session, redis_state):
    order = _make_order(db_session)
    _make_run(db_session, order, resolution="CONTACT_CUSTOMER")
    _make_ticket(db_session, order)
    redis_state["dead_letters"] = {"TICKET_CREATED": "boom"}

    timeline = build_order_timeline(db_session, order.id)

    assert timeline["state"] == "failed"
    assert _stages(timeline)["triage"]["status"] == "failed"


class _FakeRedis:
    def __init__(self, last_delivered="0-0", stream=(), dead_letters=()):
        self.last_delivered = last_delivered
        self.stream = list(stream)
        self.dead_letters = list(dead_letters)

    def xinfo_groups(self, _stream):
        return [
            {"name": "other-group", "last-delivered-id": "999-0"},
            {
                "name": order_timeline.CONSUMER_GROUP,
                "last-delivered-id": self.last_delivered,
            },
        ]

    def xrange(self, _stream, min, max):
        lo, hi = order_timeline._stream_id(min[1:]), order_timeline._stream_id(max[1:])
        return [(i, {}) for i in self.stream if lo < order_timeline._stream_id(i) < hi]

    def xrevrange(self, _stream, count):
        return self.dead_letters[:count]


def test_queue_position_counts_events_ahead():
    fake = _FakeRedis(last_delivered="2-0", stream=["1-0", "2-0", "3-0", "4-0", "5-0"])
    with patch.object(order_timeline, "redis_client", fake):
        assert order_timeline._queue_position("5-0") == {
            "picked_up": False,
            "ahead": 2,
        }


def test_queue_position_detects_pickup():
    # Numeric, not string, comparison: "10-0" > "9-0" even though "1" < "9".
    fake = _FakeRedis(last_delivered="10-0")
    with patch.object(order_timeline, "redis_client", fake):
        assert order_timeline._queue_position("9-0")["picked_up"] is True


def test_dead_letters_match_by_event_id_or_order_id():
    import json

    fake = _FakeRedis(
        dead_letters=[
            (
                "3-0",
                {
                    "event": json.dumps(
                        {"event_type": "TICKET_CREATED", "data": {"order_id": 7}}
                    ),
                    "error": "triage failed",
                },
            ),
            (
                "2-0",
                {
                    "event": json.dumps(
                        {"event_type": "ORDER_DELAYED", "event_id": "evt-x", "data": {}}
                    ),
                    "error": "agent failed",
                },
            ),
            (
                "1-0",
                {
                    "event": json.dumps(
                        {"event_type": "ORDER_DELAYED", "data": {"order_id": 8}}
                    ),
                    "error": "other order",
                },
            ),
        ]
    )
    with patch.object(order_timeline, "redis_client", fake):
        assert order_timeline._dead_letters_for(7, "evt-x") == {
            "TICKET_CREATED": "triage failed",
            "ORDER_DELAYED": "agent failed",
        }


def _make_triage_run(db_session, ticket, event_id="evt-t"):
    run = AgentExecution(
        agent_name="triage_agent",
        event_id=event_id,
        order_id=ticket.order_id,
        input_data={"ticket_id": ticket.id},
        decision={"intent": "WRONG_ITEM", "priority": "HIGH"},
    )
    db_session.add(run)
    db_session.commit()
    return run


def test_ticket_timeline_returns_none_for_unknown_ticket(db_session, redis_state):
    assert order_timeline.build_ticket_timeline(db_session, 999) is None


def test_ticket_timeline_waiting_in_queue(db_session, redis_state):
    ticket = _make_ticket(db_session, _make_order(db_session))
    redis_state["queue"] = {"picked_up": False, "ahead": 2}

    timeline = order_timeline.build_ticket_timeline(
        db_session, ticket.id, "evt-t", "9-0"
    )

    stages = _stages(timeline)
    assert timeline["state"] == "in_progress"
    assert stages["ticket_created"]["detail"]["subject"] == "ESCALATED"
    assert stages["event_queued"]["detail"]["queue"]["ahead"] == 2
    assert stages["triage"]["status"] == "pending"


def test_ticket_timeline_complete_after_triage(db_session, redis_state):
    ticket = _make_ticket(db_session, _make_order(db_session))
    _make_triage_run(db_session, ticket)

    timeline = order_timeline.build_ticket_timeline(db_session, ticket.id, "evt-t")

    triage = _stages(timeline)["triage"]
    assert timeline["state"] == "complete"
    assert triage["detail"]["decision"]["intent"] == "WRONG_ITEM"
    assert triage["detail"]["ticket"]["id"] == ticket.id


def test_ticket_timeline_finds_run_without_event_id(db_session, redis_state):
    order = _make_order(db_session)
    other = _make_ticket(db_session, order)
    ticket = _make_ticket(db_session, order)
    _make_triage_run(db_session, other, event_id="evt-other")
    _make_triage_run(db_session, ticket, event_id="evt-mine")

    timeline = order_timeline.build_ticket_timeline(db_session, ticket.id)

    assert _stages(timeline)["triage"]["detail"]["event_id"] == "evt-mine"


def test_ticket_timeline_dead_lettered(db_session, redis_state):
    ticket = _make_ticket(db_session, _make_order(db_session))
    redis_state["dead_letters"] = {"TICKET_CREATED": "triage blew up"}

    timeline = order_timeline.build_ticket_timeline(db_session, ticket.id, "evt-t")

    assert timeline["state"] == "failed"
    assert _stages(timeline)["triage"]["detail"]["error"] == "triage blew up"


def test_dead_letters_without_order_id_dont_match_orderless_events():
    """order_id=None must not match events whose data has no order_id
    (None == None) — only the explicit event_id should match."""
    import json

    fake = _FakeRedis(
        dead_letters=[
            (
                "1-0",
                {
                    "event": json.dumps({"event_type": "TICKET_CREATED", "data": {}}),
                    "error": "someone else's",
                },
            )
        ]
    )
    with patch.object(order_timeline, "redis_client", fake):
        assert order_timeline._dead_letters_for(None, "evt-mine") == {}


def test_ticket_timeline_lists_customer_emails(db_session, redis_state):
    from app.models.notification import Notification

    ticket = _make_ticket(db_session, _make_order(db_session))
    db_session.add(
        Notification(
            customer_id=ticket.customer_id,
            order_id=ticket.order_id,
            channel="EMAIL",
            recipient="c@example.com",
            subject=f"We've received your request (ticket #{ticket.id})",
            content="ack",
            status="SENT",
        )
    )
    db_session.commit()

    stage = _stages(order_timeline.build_ticket_timeline(db_session, ticket.id))[
        "notifications"
    ]

    assert stage["status"] == "done"
    assert stage["detail"]["notifications"][0]["subject"].startswith("We've received")
