from app.api.admin import get_usage
from app.models.agent_execution import AgentExecution


def _make_execution(db_session, **overrides) -> AgentExecution:
    execution = AgentExecution(
        agent_name=overrides.pop("agent_name", "delayed_order_agent"),
        event_id=overrides.pop("event_id", "evt-1"),
        input_data=overrides.pop("input_data", {"order_id": 1}),
        decision=overrides.pop("decision", {"trace_id": "trace-1"}),
        model=overrides.pop("model", "llama-3.1-8b-instant"),
        input_tokens=overrides.pop("input_tokens", 100),
        output_tokens=overrides.pop("output_tokens", 50),
        total_tokens=overrides.pop("total_tokens", 150),
        llm_call_count=overrides.pop("llm_call_count", 1),
        duration_ms=overrides.pop("duration_ms", 500),
        task_id=overrides.pop("task_id", None),
        order_id=overrides.pop("order_id", None),
    )
    db_session.add(execution)
    db_session.commit()
    db_session.refresh(execution)
    return execution


def test_get_usage_returns_empty_summary_when_no_runs(db_session):
    result = get_usage(db=db_session)

    assert result["summary"]["total_executions"] == 0
    assert result["summary"]["total_cost_usd"] == 0.0
    assert result["by_agent"] == []
    assert result["recent"] == []


def test_get_usage_aggregates_across_runs(db_session):
    _make_execution(
        db_session,
        agent_name="delayed_order_agent",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
    )
    _make_execution(
        db_session,
        agent_name="delayed_order_agent",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
    )
    _make_execution(
        db_session,
        agent_name="triage_agent",
        input_tokens=40,
        output_tokens=20,
        total_tokens=60,
    )

    result = get_usage(db=db_session)

    assert result["summary"]["total_executions"] == 3
    assert result["summary"]["total_input_tokens"] == 340
    assert result["summary"]["total_output_tokens"] == 170
    assert result["summary"]["total_tokens"] == 510
    assert result["summary"]["total_llm_calls"] == 3
    assert result["summary"]["cost_incomplete"] is False
    assert result["summary"]["total_cost_usd"] > 0

    by_agent = {row["agent_name"]: row for row in result["by_agent"]}
    assert by_agent["delayed_order_agent"]["executions"] == 2
    assert by_agent["delayed_order_agent"]["total_tokens"] == 450
    assert by_agent["triage_agent"]["executions"] == 1


def test_get_usage_recent_includes_trace_id_and_is_most_recent_first(db_session):
    first = _make_execution(db_session, decision={"trace_id": "trace-a"})
    second = _make_execution(db_session, decision={"trace_id": "trace-b"})

    result = get_usage(db=db_session)

    assert [row["id"] for row in result["recent"]] == [second.id, first.id]
    assert result["recent"][0]["trace_id"] == "trace-b"


def test_get_usage_respects_limit(db_session):
    for i in range(5):
        _make_execution(db_session, event_id=f"evt-{i}")

    result = get_usage(limit=2, db=db_session)

    assert len(result["recent"]) == 2
    # Summary/by_agent stay all-time even when the recent list is capped.
    assert result["summary"]["total_executions"] == 5


def test_get_usage_flags_cost_incomplete_for_unknown_model(db_session):
    _make_execution(
        db_session, model="some-unpriced-model", input_tokens=10, output_tokens=5
    )

    result = get_usage(db=db_session)

    assert result["summary"]["cost_incomplete"] is True
    assert result["by_agent"][0]["cost_usd"] is None
    assert result["recent"][0]["cost_usd"] is None


def test_get_usage_groups_runs_into_tasks(db_session):
    # Delayed order -> agent-created ticket -> triage: one task.
    _make_execution(
        db_session,
        agent_name="delayed_order_agent",
        event_id="evt-order",
        task_id="evt-order",
        order_id=10,
        input_data={"order_id": 10},
        input_tokens=1000,
        output_tokens=200,
        total_tokens=1200,
        llm_call_count=5,
    )
    _make_execution(
        db_session,
        agent_name="triage_agent",
        event_id="evt-ticket",
        task_id="evt-order",
        order_id=10,
        input_data={"ticket_id": 3},
        input_tokens=300,
        output_tokens=100,
        total_tokens=400,
        llm_call_count=1,
    )
    # Customer-filed ticket: its own task.
    _make_execution(
        db_session,
        agent_name="triage_agent",
        event_id="evt-complaint",
        task_id="evt-complaint",
        order_id=10,
        input_data={"ticket_id": 4},
    )
    # Pre-task_id row: falls back to its own event_id.
    _make_execution(db_session, event_id="evt-legacy", task_id=None)

    tasks = {t["task_id"]: t for t in get_usage(db=db_session)["tasks"]}

    assert set(tasks) == {"evt-order", "evt-complaint", "evt-legacy"}

    order_task = tasks["evt-order"]
    assert order_task["kind"] == "delayed_order"
    assert order_task["order_id"] == 10
    assert order_task["agents"] == ["delayed_order_agent", "triage_agent"]
    assert order_task["total_tokens"] == 1600
    assert order_task["llm_call_count"] == 6
    assert [r["agent_name"] for r in order_task["runs"]] == [
        "delayed_order_agent",
        "triage_agent",
    ]

    complaint = tasks["evt-complaint"]
    assert complaint["kind"] == "customer_ticket"
    assert complaint["ticket_id"] == 4
    assert complaint["agents"] == ["triage_agent"]


def test_task_cost_flags_unpriced_runs(db_session):
    _make_execution(db_session, task_id="t1", model="llama-3.1-8b-instant")
    _make_execution(db_session, task_id="t1", event_id="evt-2", model="unpriced-model")

    task = get_usage(db=db_session)["tasks"][0]

    assert task["cost_usd"] is not None  # the priced run still counts
    assert task["cost_incomplete"] is True
