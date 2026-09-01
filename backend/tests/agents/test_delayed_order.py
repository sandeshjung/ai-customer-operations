from app.agents.models import AgentDecision
from app.agents.guardrails import validate_decision
import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage

from backend.app.agents.graphs.delayed_order import should_continue


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
    result = get_order.invoke(
        {
            "order_id": 99999999
        }
    )

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
                "args": {
                    "order_id": 10024
                },
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

    with patch(
        "app.agents.graphs.delayed_order.llm"
    ) as mock_llm:

        mock_llm.invoke.return_value = FakeResponse()

        from app.agents.graphs.delayed_order import decision_node

        with pytest.raises(
            ValueError,
            match="Invalid decision JSON"
        ):
            decision_node(state)

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

    with patch(
        "app.agents.graphs.delayed_order.llm"
    ) as mock_llm:

        mock_llm.invoke.return_value = FakeResponse()

        from app.agents.graphs.delayed_order import decision_node

        result = decision_node(state)

    assert result["decision"].severity == "HIGH"

    assert (

        result["decision"].resolution
        == "CONTACT_CARRIER"
    )

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

    with patch(
        "app.agents.graphs.delayed_order.llm"
    ) as mock_llm:

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

    with patch(
        "app.agents.graphs.delayed_order.llms_with_tools"
    ) as mock_agent_llm, patch(
        "app.agents.graphs.delayed_order.llm"
    ) as mock_decision_llm:

        mock_agent_llm.invoke.return_value = (
            fake_agent_response
        )

        mock_decision_llm.invoke.return_value = (
            FakeDecisionResponse()
        )

        from app.agents.graphs.delayed_order import (
            delayed_order_graph,
        )

        result = delayed_order_graph.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Investigate delayed order 10024."
                        ),
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

    assert (
        result["decision"].resolution
        == "CONTACT_CARRIER"
    )

    assert result["requires_human"] is False