import json 
import logging
import re
import time
from langchain_core.messages import (
    HumanMessage, 
    SystemMessage,
    ToolMessage
)
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.agents.models import AgentDecision
from app.agents.state import DelayedOrderState
from app.ai.client import client
from app.core.config import settings
from app.core.tracing import current_trace_id, traced
from app.rag.service import retrieve_policy
from app.agents.guardrails import validate_decision

from langchain_groq import ChatGroq
from langchain_core.tools import tool

from app.core.logging import configure_logging
configure_logging()

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5

llm = ChatGroq(
    model=settings.LLM_MODEL,
    api_key=settings.LLM_API_KEY,
    temperature=0
)

@tool 
def get_order(order_id: int) -> str:
    """Get order information by order ID."""

    logger.info(
        "Calling get_order tool",
        extra={"order_id": order_id},
    )

    from app.core.database import SessionLocal
    from app.agents.tools.order_tools import get_order as db_get_order

    with traced("tool.get_order", tracer_name="delayed_order_agent", order_id=order_id) as span:
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
    
    from app.core.database import SessionLocal
    from app.agents.tools.shipment_tools import get_shipment as db_get_shipment

    with traced("tool.get_shipment", tracer_name="delayed_order_agent", order_id=order_id) as span:
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

    from app.core.database import SessionLocal
    from app.agents.tools.customer_tools import get_customer as db_get_customer

    with traced("tool.get_customer", tracer_name="delayed_order_agent", customer_id=customer_id) as span:
        db = SessionLocal()
        try:
            result = db_get_customer(db, customer_id)
            span.set_attribute("found", result is not None)
            return json.dumps(result or {"error": "Customer not found"})
        finally:
            db.close()


@tool
def search_shipping_policy(query: str) -> str:
    """Search company policies and support documentation."""
    with traced("tool.search_shipping_policy", tracer_name="delayed_order_agent", query=query[:200]) as span:
        results = retrieve_policy(query=query, limit=5)
        span.set_attribute("result_count", len(results))
        return json.dumps(results, ensure_ascii=False)

tools = [
    get_order,
    get_shipment,
    get_customer,
    search_shipping_policy
]

llms_with_tools = llm.bind_tools(tools)

SYSTEM_PROMPT = """
You are an AI operations agent responsible for investigating delayed orders.

You are given an order ID and the number of days the order is delayed.

Your job is to investigate the situation.

Use tools when you need additional information.

You should generally investigate:

1. The order.
2. The shipment.
3. The customer when customer information is relevant.

Never invent information.

If shipment information is missing, treat that as an important
operational signal.

After gathering enough information, determine:

- severity
- recommended resolution
- whether human intervention is required
- an optional customer message

You must not perform actions that modify the database.

You are an investigation and recommendation agent only.

When determining an operational resolution, use
search_shipping_policy to retrieve relevant company policy.

Do not rely on general knowledge for company policies.

If a policy is relevant to the decision, retrieve it
before making the decision.

Never invent policy rules.
"""

def agent_node(
    state: DelayedOrderState
):
    messages = state["messages"]

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
        response = llms_with_tools.invoke([
            SystemMessage(content=SYSTEM_PROMPT),   # ← tells LLM to investigate using tools
            *state["messages"]
        ])

        tool_calls = getattr(response, "tool_calls", [])
        span.set_attribute("tool_calls_count", len(tool_calls))
        if tool_calls:
            span.set_attribute("tool_calls", ",".join(tc["name"] for tc in tool_calls))
        usage = getattr(response, "usage_metadata", None)
        if usage:
            span.set_attribute("llm.input_tokens", usage.get("input_tokens", 0))
            span.set_attribute("llm.output_tokens", usage.get("output_tokens", 0))
            span.set_attribute("llm.total_tokens", usage.get("total_tokens", 0))

    latency_ms = (
        time.perf_counter() - start_time
    ) * 1000

    logger.info(
        "LLM completed | order_id=%s | latency_ms=%.2f | tool_calls=%s",
        state["order_id"],
        latency_ms,
        len(getattr(response, "tool_calls", [])),
    )

    return {
        "messages": [response]
    }

def should_continue(
    state: DelayedOrderState
):
    if state["tool_iterations"] >= MAX_TOOL_ITERATIONS:
        return "decision"
    
    last_message = state["messages"][-1]

    if getattr(
        last_message,
        "tool_calls",
        None
    ):
        return "tools"
    return "decision"

# tool_node = ToolNode(tools)

def tool_node(
        state: DelayedOrderState
):
    current_iterations = state["tool_iterations"]

    logger.info(
        "Tool execution | order_id=%s | iteration=%s",
        state["order_id"],
        current_iterations + 1,
    )

    if current_iterations >= MAX_TOOL_ITERATIONS:

        logger.warning(
            "Tool iteration limit reached | order_id=%s",
            state["order_id"],
        )
        return {
            "requires_human": True,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Maximum tool-call iterations reached."
                        "Escalate to human review."
                    )
                }
            ]
        }
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

    return {
        **result,
        "tool_iterations": current_iterations + 1
    }

DECISION_PROMPT = """
Based on the investigation above, produce the final operational decision.

If policy documents were retrieved, use them as the source of truth.

Return ONLY valid JSON. Do not use markdown code blocks. Do not add explanations before or after the JSON. The response must start with { and end with }.

{
  "severity": "LOW | MEDIUM | HIGH | CRITICAL",
  "resolution": "TRACK_SHIPMENT | CONTACT_CARRIER | CONTACT_CUSTOMER | ESCALATE | NO_ACTION",
  "reasoning": "short explanation",
  "customer_message": "message or null",
  "requires_human": true,
  "evidence": [
    {
      "source": "shipping_policy.pdf",
      "page": 2,
      "chunk_index": 1
    }
  ]
}

Rules:

- Never invent policy information.
- Only include evidence that was actually retrieved.
- If no policy was retrieved, return an empty evidence list.
"""

def decision_node(
    state: DelayedOrderState
):
    logger.info(
        "Generating final decision | order_id=%s",
        state["order_id"],
    )

    start_time = time.perf_counter()

    # Use the tool-bound LLM so the model can call tools during decision
    # generation (some decisions request policy lookups or documents).
    with traced(
        "llm.decision",
        tracer_name="delayed_order_agent",
        order_id=state["order_id"],
        model=settings.LLM_MODEL,
    ) as span:
        response = llms_with_tools.invoke(
            [
                SystemMessage(content=DECISION_PROMPT),
                *state["messages"],
            ]
        )
        usage = getattr(response, "usage_metadata", None)
        if usage:
            span.set_attribute("llm.input_tokens", usage.get("input_tokens", 0))
            span.set_attribute("llm.output_tokens", usage.get("output_tokens", 0))
            span.set_attribute("llm.total_tokens", usage.get("total_tokens", 0))

    # latency_ms = (
    #     time.perf_counter() - start_time
    # ) * 1000

    # content = getattr(response, "content", None)
    # if not isinstance(content, str):
    #     raise ValueError("Unexpected LLM response format")

    # try:
    #     decision_data = json.loads(content)
    # except json.JSONDecodeError as exc:
    #     raise ValueError(
    #         f"Invalid decision JSON: {content}"
    #     ) from exc

    # decision = AgentDecision.model_validate(decision_data)
    # structured_llm = llm.with_structured_output(AgentDecision)
    # decision = structured_llm.invoke(
    #     [
    #         SystemMessage(content=DECISION_PROMPT),
    #         *state["messages"],
    #     ]
    # )

    latency_ms = (time.perf_counter() - start_time) * 1000
    content = response.content.strip()

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
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            raise ValueError(f"Invalid decision JSON: {content[:500]}")
        decision_data = json.loads(match.group())

    decision = AgentDecision.model_validate(decision_data)
    decision = validate_decision(decision)
    decision.trace_id = current_trace_id()

    logger.info(
        "Decision generated | order_id=%s | severity=%s | resolution=%s | requires_human=%s | latency_ms=%.2f | reason=%s | trace_id=%s",
        state["order_id"],
        decision.severity,
        decision.resolution,
        decision.requires_human,
        latency_ms,
        decision.reasoning,
        decision.trace_id,
    )

    return {
        "decision": decision,
        "requires_human": decision.requires_human,
        "evidence": [
            evidence.model_dump()
            for evidence in decision.evidence
        ],
    }


graph_builder = StateGraph(
    DelayedOrderState
)

graph_builder.add_node(
    "agent",
    agent_node
)

graph_builder.add_node(
    "tools",
    tool_node
)

graph_builder.add_node(
    "decision",
    decision_node
)

graph_builder.add_edge(
    START,
    "agent"
)

graph_builder.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        "decision": "decision"
    }
)

graph_builder.add_edge(
    "tools",
    "agent"
)

graph_builder.add_edge(
    "decision",
    END
)

delayed_order_graph = graph_builder.compile()