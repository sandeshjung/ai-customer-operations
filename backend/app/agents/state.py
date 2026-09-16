from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class DelayedOrderState(TypedDict):
    messages: Annotated[list, add_messages]

    order_id: int

    order: dict | None
    shipment: dict | None
    customer: dict | None

    delay_days: int

    decision: dict | None

    requires_human: bool

    tool_iterations: int

    evidence: list[dict]

    # Cumulative usage across every LLM call in this graph run (agent_node
    # loops + decision_node) — read back by agent_service.py once the graph
    # finishes, for the AI usage monitor.
    llm_input_tokens: int
    llm_output_tokens: int
    llm_total_tokens: int
    llm_call_count: int
