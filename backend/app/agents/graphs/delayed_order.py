import json
import logging
import re
import time

from app.agents.guardrails import validate_decision
from app.agents.models import AgentDecision
from app.agents.prompts import (
    DELAYED_ORDER_AGENT_PROMPT,
    DELAYED_ORDER_DECISION_PROMPT,
)
from app.agents.state import DelayedOrderState
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.tracing import current_trace_id, inject_trace_context, traced
from app.rag.service import retrieve_policy
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import ValidationError

configure_logging()

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5

llm = ChatGroq(
    model=settings.LLM_MODEL,
    api_key=settings.LLM_API_KEY,
    temperature=0,
    max_retries=settings.LLM_MAX_RETRIES,
)


@tool
def get_order(order_id: int) -> str:
    """Get order information by order ID."""

    logger.info(
        "Calling get_order tool",
        extra={"order_id": order_id},
    )

    from app.agents.tools.order_tools import get_order as db_get_order
    from app.core.database import SessionLocal

    with traced(
        "tool.get_order", tracer_name="delayed_order_agent", order_id=order_id
    ) as span:
        db = SessionLocal()
        try:
            result = db_get_order(db, order_id)
            span.set_attribute("found", result is not None)
            return json.dumps(result or {"error": "Order not found"})
        finally:
            db.close()


@tool
def get_shipment(order_id: int) -> str:
    """Get shipment information for an order."""  # ← fixed: was """" (4 quotes)

    logger.info(
        "Calling get_shipment tool",
        extra={"order_id": order_id},
    )

    from app.agents.tools.shipment_tools import get_shipment as db_get_shipment
    from app.core.database import SessionLocal

    with traced(
        "tool.get_shipment", tracer_name="delayed_order_agent", order_id=order_id
    ) as span:
        db = SessionLocal()
        try:
            result = db_get_shipment(db, order_id)
            span.set_attribute("found", result is not None)
            return json.dumps(result or {"error": "Shipment not found"})
        finally:
            db.close()


@tool
def get_customer(customer_id: int) -> str:
    """Get customer information."""

    logger.info(
        "Calling get_customer tool",
        extra={"customer_id": customer_id},
    )

    from app.agents.tools.customer_tools import get_customer as db_get_customer
    from app.core.database import SessionLocal

    with traced(
        "tool.get_customer", tracer_name="delayed_order_agent", customer_id=customer_id
    ) as span:
        db = SessionLocal()
        try:
            result = db_get_customer(db, customer_id)
            span.set_attribute("found", result is not None)
            return json.dumps(result or {"error": "Customer not found"})
        finally:
            db.close()


_POLICY_RESULT_KEYS = ("content", "source", "page", "chunk_index")


@tool
def search_shipping_policy(query: str) -> str:
    """Search company policies and support documentation."""
    with traced(
        "tool.search_shipping_policy",
        tracer_name="delayed_order_agent",
        query=query[:200],
    ) as span:
        results = retrieve_policy(query=query, limit=5)
        span.set_attribute("result_count", len(results))
        # Only what the model needs to reason and cite evidence. Retrieval
        # scores and the doc version would be resent on every later LLM call.
        return json.dumps(
            [
                {key: r.get(key) for key in _POLICY_RESULT_KEYS}
                for r in results
                if isinstance(r, dict)
            ],
            ensure_ascii=False,
        )


tools = [get_order, get_shipment, get_customer, search_shipping_policy]


def _usage_delta(state: DelayedOrderState, usage: dict | None) -> dict:
    """Adds one LLM call's usage_metadata onto the state's running totals."""
    delta = {"llm_call_count": state.get("llm_call_count", 0) + 1}
    if usage:
        delta["llm_input_tokens"] = state.get("llm_input_tokens", 0) + usage.get(
            "input_tokens", 0
        )
        delta["llm_output_tokens"] = state.get("llm_output_tokens", 0) + usage.get(
            "output_tokens", 0
        )
        delta["llm_total_tokens"] = state.get("llm_total_tokens", 0) + usage.get(
            "total_tokens", 0
        )
    return delta


llms_with_tools = llm.bind_tools(tools)


def agent_node(state: DelayedOrderState):
    logger.info(
        "Agent execution | order_id=%s | tool_iteration=%s",
        state["order_id"],
        state["tool_iterations"],
    )

    start_time = time.perf_counter()

    with traced(
        "llm.agent_step",
        tracer_name="delayed_order_agent",
        order_id=state["order_id"],
        tool_iteration=state["tool_iterations"],
        model=settings.LLM_MODEL,
    ) as span:
        response = llms_with_tools.invoke(
            [
                # Investigation instructions plus the decision format.
                SystemMessage(content=DELAYED_ORDER_AGENT_PROMPT),
                *state["messages"],
            ]
        )

        tool_calls = getattr(response, "tool_calls", [])
        span.set_attribute("tool_calls_count", len(tool_calls))
        if tool_calls:
            span.set_attribute("tool_calls", ",".join(tc["name"] for tc in tool_calls))
        usage = getattr(response, "usage_metadata", None)
        if usage:
            span.set_attribute("llm.input_tokens", usage.get("input_tokens", 0))
            span.set_attribute("llm.output_tokens", usage.get("output_tokens", 0))
            span.set_attribute("llm.total_tokens", usage.get("total_tokens", 0))

    latency_ms = (time.perf_counter() - start_time) * 1000

    logger.info(
        "LLM completed | order_id=%s | latency_ms=%.2f | tool_calls=%s",
        state["order_id"],
        latency_ms,
        len(getattr(response, "tool_calls", [])),
    )

    return {"messages": [response], **_usage_delta(state, usage)}


def should_continue(state: DelayedOrderState):
    if state["tool_iterations"] >= MAX_TOOL_ITERATIONS:
        return "decision"

    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "tools"
    return "decision"


# tool_node = ToolNode(tools)


def tool_node(state: DelayedOrderState):
    current_iterations = state["tool_iterations"]

    logger.info(
        "Tool execution | order_id=%s | iteration=%s",
        state["order_id"],
        current_iterations + 1,
    )

    tool_calls = getattr(state["messages"][-1], "tool_calls", []) or []
    with traced(
        "tools.execute_batch",
        tracer_name="delayed_order_agent",
        order_id=state["order_id"],
        iteration=current_iterations + 1,
        tool_names=",".join(tc["name"] for tc in tool_calls) if tool_calls else "",
    ):
        tool_executor = ToolNode(tools)
        result = tool_executor.invoke(state)

    logger.info(
        "Tools completed | order_id=%s | iteration=%s",
        state["order_id"],
        current_iterations + 1,
    )

    return {**result, "tool_iterations": current_iterations + 1}


def _parse_decision(content: str) -> AgentDecision:
    content = content.strip()

    # Strip markdown fences
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        decision_data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError(f"Invalid decision JSON: {content[:500]}")
        decision_data = json.loads(match.group())

    return AgentDecision.model_validate(decision_data)


def _decision_from_agent_turn(state: DelayedOrderState) -> AgentDecision | None:
    """The agent's prompt asks it to answer with the decision JSON once it
    stops calling tools, so that turn usually already is the decision. Returns
    None when it isn't (tool cap hit mid-loop, or prose instead of JSON)."""
    if not state["messages"]:
        return None
    last = state["messages"][-1]
    if getattr(last, "type", None) != "ai" or getattr(last, "tool_calls", None):
        return None
    content = getattr(last, "content", None)
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        return _parse_decision(content)
    except (ValueError, ValidationError):
        return None


def decision_node(state: DelayedOrderState):
    logger.info(
        "Generating final decision | order_id=%s",
        state["order_id"],
    )

    start_time = time.perf_counter()
    usage_delta: dict = {}

    decision = _decision_from_agent_turn(state)
    if decision is None:
        # Fallback: one more call that asks only for the decision. Uses the
        # tool-bound LLM because the history contains tool calls.
        with traced(
            "llm.decision",
            tracer_name="delayed_order_agent",
            order_id=state["order_id"],
            model=settings.LLM_MODEL,
        ) as span:
            response = llms_with_tools.invoke(
                [
                    SystemMessage(content=DELAYED_ORDER_DECISION_PROMPT),
                    *state["messages"],
                ]
            )
            usage = getattr(response, "usage_metadata", None)
            if usage:
                span.set_attribute("llm.input_tokens", usage.get("input_tokens", 0))
                span.set_attribute("llm.output_tokens", usage.get("output_tokens", 0))
                span.set_attribute("llm.total_tokens", usage.get("total_tokens", 0))
        usage_delta = _usage_delta(state, usage)
        decision = _parse_decision(response.content)

    latency_ms = (time.perf_counter() - start_time) * 1000

    decision = validate_decision(decision)
    # should_continue() routes here once the tool loop hits its cap, so the
    # model may be deciding on incomplete evidence: never auto-execute that.
    if state.get("tool_iterations", 0) >= MAX_TOOL_ITERATIONS:
        decision.requires_human = True
    decision.trace_id = current_trace_id()
    # Carrier for the approval path: approve() runs long after this trace has
    # closed, so it Links back to this span instead of parenting under it.
    decision.trace_context = inject_trace_context() or None

    logger.info(
        "Decision generated | order_id=%s | severity=%s | resolution=%s | requires_human=%s | latency_ms=%.2f | extra_llm_call=%s | reason=%s | trace_id=%s",
        state["order_id"],
        decision.severity,
        decision.resolution,
        decision.requires_human,
        latency_ms,
        bool(usage_delta),
        decision.reasoning,
        decision.trace_id,
    )

    return {
        "decision": decision,
        "requires_human": decision.requires_human,
        "evidence": [evidence.model_dump() for evidence in decision.evidence],
        **usage_delta,
    }


graph_builder = StateGraph(DelayedOrderState)

graph_builder.add_node("agent", agent_node)

graph_builder.add_node("tools", tool_node)

graph_builder.add_node("decision", decision_node)

graph_builder.add_edge(START, "agent")

graph_builder.add_conditional_edges(
    "agent", should_continue, {"tools": "tools", "decision": "decision"}
)

graph_builder.add_edge("tools", "agent")

graph_builder.add_edge("decision", END)

delayed_order_graph = graph_builder.compile()
