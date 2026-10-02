import sys
import types
from unittest.mock import patch

# Importing app.services.agent_service transitively imports
# app.agents.graphs.delayed_order -> app.rag.service, which loads a real
# HuggingFace embedding model and a real Qdrant client at *module import
# time* (see CLAUDE.md gotcha #1). Stub it out before the import below,
# the same way test_triage_service.py and test_event_consumer.py do.
sys.modules["app.rag.service"] = types.ModuleType("app.rag.service")
sys.modules["app.rag.service"].retrieve_policy = lambda query, limit=5: []

from app.agents.models import AgentDecision, DelaySeverity, ResolutionType
from app.models.agent_execution import AgentExecution
from app.services import agent_service


def _make_decision(**overrides) -> AgentDecision:
    fields = {
        "severity": DelaySeverity.LOW,
        "resolution": ResolutionType.TRACK_SHIPMENT,
        "reasoning": "Shipment is on schedule, just slightly delayed.",
        "requires_human": False,
    }
    fields.update(overrides)
    return AgentDecision(**fields)


def test_persists_agent_execution_with_token_usage(db_session):
    """Regression test for the AI usage monitor: token/cost data must reach
    agent_executions, not just OTel spans, so it's queryable from the admin
    console rather than only visible in Jaeger."""
    decision = _make_decision()

    with patch.object(agent_service, "delayed_order_graph") as mock_graph:
        mock_graph.invoke.return_value = {
            "decision": decision,
            "llm_input_tokens": 300,
            "llm_output_tokens": 120,
            "llm_total_tokens": 420,
            "llm_call_count": 3,
        }
        agent_service.investigate_delayed_order(
            db=db_session, order_id=1, delay_days=5, event_id="evt-1"
        )

    execution = (
        db_session.query(AgentExecution)
        .filter_by(agent_name="delayed_order_agent", event_id="evt-1")
        .one()
    )
    assert execution.input_tokens == 300
    assert execution.output_tokens == 120
    assert execution.total_tokens == 420
    assert execution.llm_call_count == 3
    assert execution.duration_ms is not None
    assert execution.model is not None


def test_missing_usage_keys_default_to_zero(db_session):
    """The graph result may lack llm_* keys entirely (e.g. an older cached
    result) — persistence shouldn't crash, just record zero usage."""
    decision = _make_decision()

    with patch.object(agent_service, "delayed_order_graph") as mock_graph:
        mock_graph.invoke.return_value = {"decision": decision}
        agent_service.investigate_delayed_order(
            db=db_session, order_id=2, delay_days=3, event_id="evt-2"
        )

    execution = (
        db_session.query(AgentExecution)
        .filter_by(agent_name="delayed_order_agent", event_id="evt-2")
        .one()
    )
    assert execution.input_tokens == 0
    assert execution.output_tokens == 0
    assert execution.total_tokens == 0
    assert execution.llm_call_count == 0


def test_persists_order_id_and_tool_steps(db_session):
    """The admin console's order timeline reads these — order_id to find the
    run, steps to show which tools the agent called and what came back."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    messages = [
        HumanMessage(content="Investigate delayed order 7."),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_order", "args": {"order_id": 7}, "id": "c1"},
                {"name": "get_shipment", "args": {"order_id": 7}, "id": "c2"},
            ],
        ),
        ToolMessage(content='{"status": "LOST"}', tool_call_id="c2"),
        ToolMessage(content='{"id": 7}', tool_call_id="c1"),
        AIMessage(content="done"),
    ]

    with patch.object(agent_service, "delayed_order_graph") as mock_graph:
        mock_graph.invoke.return_value = {
            "decision": _make_decision(),
            "messages": messages,
        }
        agent_service.investigate_delayed_order(
            db=db_session, order_id=7, delay_days=4, event_id="evt-steps"
        )

    execution = db_session.query(AgentExecution).filter_by(event_id="evt-steps").one()
    assert execution.order_id == 7
    assert execution.steps == [
        {"tool": "get_order", "args": {"order_id": 7}, "result": '{"id": 7}'},
        {
            "tool": "get_shipment",
            "args": {"order_id": 7},
            "result": '{"status": "LOST"}',
        },
    ]


def test_extract_tool_steps_truncates_long_results():
    from langchain_core.messages import AIMessage, ToolMessage

    steps = agent_service.extract_tool_steps(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_shipping_policy", "args": {}, "id": "c1"}],
            ),
            ToolMessage(content="x" * 5000, tool_call_id="c1"),
        ]
    )
    assert len(steps[0]["result"]) == agent_service.MAX_STEP_RESULT_CHARS
