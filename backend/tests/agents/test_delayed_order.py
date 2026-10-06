from unittest.mock import patch

import pytest
from app.agents.graphs.delayed_order import should_continue
from app.agents.guardrails import validate_decision
from app.agents.models import AgentDecision
from langchain_core.messages import AIMessage
from pydantic import ValidationError


def test_valid_agent_decision():
    decision = AgentDecision(
        severity="HIGH",
        resolution="CONTACT_CARRIER",
        reasoning="The shipment is significantly delayed.",
        customer_message=None,
        requires_human=False,
    )

    assert decision.severity == "HIGH"
    assert decision.resolution == "CONTACT_CARRIER"
    assert decision.requires_human is False


def test_invalid_agent_decision():

    with pytest.raises(ValidationError):
        AgentDecision(
            severity="INVALID",
            resolution="INVALID",
            reasoning="Invalid decision",
            customer_message=None,
            requires_human=False,
        )


def test_critical_decision_requires_human():

    decision = AgentDecision(
        severity="CRITICAL",
        resolution="CONTACT_CARRIER",
        reasoning="Critical delay detected.",
        customer_message=None,
        requires_human=False,
    )

    result = validate_decision(decision)

    assert result.requires_human is True


def test_escalation_requires_human():

    decision = AgentDecision(
        severity="HIGH",
        resolution="ESCALATE",
        reasoning="Shipment information is unavailable.",
        customer_message=None,
        requires_human=False,
    )

    result = validate_decision(decision)

    assert result.requires_human is True


def test_invalid_agent_decision_is_rejected():

    with pytest.raises(ValidationError):
        AgentDecision(
            severity="SUPER_BAD",
            resolution="DO_SOMETHING",
            reasoning="Invalid response",
            customer_message=None,
            requires_human=False,
        )


def test_missing_order_tool():

    from app.agents.graphs.delayed_order import (
        get_order,
    )

    # The tool itself may have a different interface
    # depending on your implementation.
    result = get_order.invoke({"order_id": 99999999})

    assert "error" in result


def test_tool_iteration_limit():

    from app.agents.graphs.delayed_order import (
        MAX_TOOL_ITERATIONS,
        should_continue,
    )

    state = {
        "messages": [],
        "order_id": 10024,
        "order": None,
        "shipment": None,
        "customer": None,
        "delay_days": 11,
        "decision": None,
        "requires_human": False,
        "tool_iterations": MAX_TOOL_ITERATIONS,
    }

    result = should_continue(state)

    assert result == "decision"


def test_agent_routes_to_tools():

    message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_order",
                "args": {"order_id": 10024},
                "id": "test-tool-call",
            }
        ],
    )

    state = {
        "messages": [message],
        "order_id": 10024,
        "order": None,
        "shipment": None,
        "customer": None,
        "delay_days": 11,
        "decision": None,
        "requires_human": False,
        "tool_iterations": 0,
    }

    result = should_continue(state)

    assert result == "tools"


def test_decision_node_rejects_invalid_json():

    class FakeResponse:
        content = "This is not valid JSON"

    state = {
        "messages": [],
        "order_id": 10024,
        "order": None,
        "shipment": None,
        "customer": None,
        "delay_days": 11,
        "decision": None,
        "requires_human": False,
        "tool_iterations": 0,
    }

    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        mock_llm.invoke.return_value = FakeResponse()

        from app.agents.graphs.delayed_order import decision_node

        with pytest.raises(ValueError, match="Invalid decision JSON"):
            decision_node(state)


def test_decision_node_parses_valid_json():

    class FakeResponse:
        content = """
        {
            "severity": "HIGH",
            "resolution": "CONTACT_CARRIER",
            "reasoning": "The shipment is significantly delayed.",
            "customer_message": null,
            "requires_human": false
        }
        """

    state = {
        "messages": [],
        "order_id": 10024,
        "order": None,
        "shipment": None,
        "customer": None,
        "delay_days": 11,
        "decision": None,
        "requires_human": False,
        "tool_iterations": 0,
    }

    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        mock_llm.invoke.return_value = FakeResponse()

        from app.agents.graphs.delayed_order import decision_node

        result = decision_node(state)

    assert result["decision"].severity == "HIGH"

    assert result["decision"].resolution == "CONTACT_CARRIER"

    assert result["requires_human"] is False


def test_decision_node_rejects_invalid_schema():

    class FakeResponse:
        content = """
        {
            "severity": "WHATEVER",
            "resolution": "DO_MAGIC",
            "reasoning": "Something happened.",
            "customer_message": null,
            "requires_human": false
        }
        """

    state = {
        "messages": [],
        "order_id": 10024,
        "order": None,
        "shipment": None,
        "customer": None,
        "delay_days": 11,
        "decision": None,
        "requires_human": False,
        "tool_iterations": 0,
    }

    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        mock_llm.invoke.return_value = FakeResponse()

        from app.agents.graphs.delayed_order import decision_node

        with pytest.raises(ValidationError):
            decision_node(state)


def test_delayed_order_graph():

    fake_agent_response = AIMessage(
        content="Investigation complete.",
        tool_calls=[],
    )

    class FakeDecisionResponse:
        content = """
        {
            "severity": "HIGH",
            "resolution": "CONTACT_CARRIER",
            "reasoning": "Order is delayed by 11 days.",
            "customer_message": null,
            "requires_human": false
        }
        """

    # agent_node and decision_node both call llms_with_tools, in that order.
    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        mock_llm.invoke.side_effect = [fake_agent_response, FakeDecisionResponse()]

        from app.agents.graphs.delayed_order import (
            delayed_order_graph,
        )

        result = delayed_order_graph.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": ("Investigate delayed order 10024."),
                    }
                ],
                "order_id": 10024,
                "order": None,
                "shipment": None,
                "customer": None,
                "delay_days": 11,
                "decision": None,
                "requires_human": False,
                "tool_iterations": 0,
            }
        )

    assert result["decision"].severity == "HIGH"

    assert result["decision"].resolution == "CONTACT_CARRIER"

    assert result["requires_human"] is False


_DECISION_JSON = """
{
    "severity": "LOW",
    "resolution": "TRACK_SHIPMENT",
    "reasoning": "Minor delay.",
    "customer_message": null,
    "requires_human": false
}
"""


def _decision_state(**overrides):
    state = {
        "messages": [],
        "order_id": 10024,
        "order": None,
        "shipment": None,
        "customer": None,
        "delay_days": 2,
        "decision": None,
        "requires_human": False,
        "tool_iterations": 0,
    }
    state.update(overrides)
    return state


def _fake_decision():
    return AIMessage(content=_DECISION_JSON)


def test_decision_node_forces_human_review_at_tool_cap():
    """Regression test: hitting MAX_TOOL_ITERATIONS used to set requires_human
    only in an unreachable tool_node branch, so a decision made on truncated
    evidence could still auto-execute."""
    from app.agents.graphs.delayed_order import MAX_TOOL_ITERATIONS, decision_node

    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        mock_llm.invoke.return_value = _fake_decision()
        result = decision_node(_decision_state(tool_iterations=MAX_TOOL_ITERATIONS))

    assert result["decision"].requires_human is True
    assert result["requires_human"] is True


def test_decision_node_below_tool_cap_keeps_model_decision():
    from app.agents.graphs.delayed_order import MAX_TOOL_ITERATIONS, decision_node

    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        mock_llm.invoke.return_value = _fake_decision()
        result = decision_node(_decision_state(tool_iterations=MAX_TOOL_ITERATIONS - 1))

    assert result["decision"].requires_human is False


def test_decision_node_captures_trace_context_for_approval_link():
    """Regression test: nothing set AgentDecision.trace_context, so approving
    a queued decision never created the OTel Link back to the agent's trace."""
    from app.agents.graphs.delayed_order import decision_node
    from app.core.tracing import link_from_carrier
    from opentelemetry.sdk.trace import TracerProvider

    tracer = TracerProvider().get_tracer("test")
    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        mock_llm.invoke.return_value = _fake_decision()
        with tracer.start_as_current_span("delayed_order_agent.run") as root:
            result = decision_node(_decision_state())
            root_trace_id = root.get_span_context().trace_id

    decision = result["decision"]
    assert decision.trace_context

    link = link_from_carrier(decision.trace_context)
    assert link is not None
    assert link.context.trace_id == root_trace_id
    assert decision.trace_id == format(root_trace_id, "032x")


def test_decision_node_without_active_span_leaves_trace_context_empty():
    from app.agents.graphs.delayed_order import decision_node

    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        mock_llm.invoke.return_value = _fake_decision()
        result = decision_node(_decision_state())

    assert result["decision"].trace_context is None


def test_get_order_tool_exposes_expected_delivery(db_session):
    """Regression test: the delivery date was returned under the key
    "expected_salary", so the agent never saw a field it could recognise."""
    from datetime import date

    from app.agents.tools.order_tools import get_order as db_get_order
    from app.models.customer import Customer
    from app.models.order import Order

    customer = Customer(name="Test Customer", email="get-order@example.com")
    db_session.add(customer)
    db_session.commit()
    order = Order(
        customer_id=customer.id,
        total_amount=42,
        expected_delivery=date(2026, 9, 1),
    )
    db_session.add(order)
    db_session.commit()

    result = db_get_order(db_session, order.id)

    assert result["expected_delivery"] == "2026-09-01"
    assert "expected_salary" not in result


def test_decision_node_reuses_agent_final_turn_without_another_llm_call():
    """The agent's prompt includes the decision format, so the turn where it
    stops calling tools already is the decision. decision_node used to make a
    second LLM call to produce the same thing."""
    from app.agents.graphs.delayed_order import decision_node

    state = _decision_state(
        messages=[AIMessage(content=_DECISION_JSON)], llm_call_count=2
    )
    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        result = decision_node(state)

    mock_llm.invoke.assert_not_called()
    assert result["decision"].resolution == "TRACK_SHIPMENT"
    # No call made, so the usage totals are left untouched.
    assert "llm_call_count" not in result


def test_decision_node_falls_back_to_llm_when_agent_answered_in_prose():
    from app.agents.graphs.delayed_order import decision_node

    state = _decision_state(messages=[AIMessage(content="Investigation complete.")])
    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        mock_llm.invoke.return_value = _fake_decision()
        result = decision_node(state)

    mock_llm.invoke.assert_called_once()
    assert result["decision"].resolution == "TRACK_SHIPMENT"
    assert result["llm_call_count"] == 1


def test_graph_makes_one_llm_call_when_agent_decides_directly():
    from app.agents.graphs.delayed_order import delayed_order_graph

    with patch("app.agents.graphs.delayed_order.llms_with_tools") as mock_llm:
        mock_llm.invoke.return_value = AIMessage(
            content=_DECISION_JSON,
            usage_metadata={
                "input_tokens": 500,
                "output_tokens": 80,
                "total_tokens": 580,
            },
        )
        result = delayed_order_graph.invoke(
            {
                **_decision_state(
                    messages=[{"role": "user", "content": "Investigate order 1."}]
                ),
                "llm_input_tokens": 0,
                "llm_output_tokens": 0,
                "llm_total_tokens": 0,
                "llm_call_count": 0,
            }
        )

    assert mock_llm.invoke.call_count == 1
    assert result["llm_call_count"] == 1
    assert result["llm_total_tokens"] == 580
    assert result["decision"].resolution == "TRACK_SHIPMENT"


def test_policy_tool_sends_only_the_fields_the_model_uses():
    import json

    from app.agents.graphs.delayed_order import search_shipping_policy

    hit = {
        "content": "Orders 5-7 days late are high priority.",
        "source": "shipping_policy.pdf",
        "page": 2,
        "chunk_index": 0,
        "version": "1.0",
        "score": 0.66,
        "rrf_score": 0.06,
    }
    with patch("app.agents.graphs.delayed_order.retrieve_policy", return_value=[hit]):
        result = json.loads(search_shipping_policy.invoke({"query": "late"}))

    assert result == [
        {
            "content": "Orders 5-7 days late are high priority.",
            "source": "shipping_policy.pdf",
            "page": 2,
            "chunk_index": 0,
        }
    ]
