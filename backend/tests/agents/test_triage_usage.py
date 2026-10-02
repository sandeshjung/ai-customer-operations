import json

from app.agents.graphs import triage_agent
from langchain_core.messages import AIMessage


class _FakeLLM:
    def invoke(self, messages):
        return AIMessage(
            content=json.dumps(
                {
                    "intent": "DELIVERY_DELAY",
                    "priority": "HIGH",
                    "sentiment": "FRUSTRATED",
                    "action": "ROUTE_TO_AGENT",
                    "reasoning": "late",
                    "requires_human": True,
                    "confidence": 0.8,
                }
            ),
            usage_metadata={
                "input_tokens": 700,
                "output_tokens": 90,
                "total_tokens": 790,
            },
        )


def test_triage_graph_returns_llm_usage(monkeypatch):
    """Regression test: TriageState didn't declare the llm_* keys, so
    LangGraph dropped them from the graph's output and every triage
    AgentExecution row recorded 0 tokens / 0 calls in the usage monitor."""
    monkeypatch.setattr(triage_agent, "llm", _FakeLLM())

    result = triage_agent.triage_graph.invoke(
        {
            "ticket_id": 1,
            "ticket": {"subject": "Late", "message": "Where?", "priority": "MEDIUM"},
            "customer_history": [],
            "policy_context": "",
        }
    )

    assert result["llm_input_tokens"] == 700
    assert result["llm_output_tokens"] == 90
    assert result["llm_total_tokens"] == 790
    assert result["llm_call_count"] == 1
