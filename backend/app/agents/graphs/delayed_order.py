import json 

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

from langchain_groq import ChatGroq

MAX_TOOL_ITERATIONS = 5

llm = ChatGroq(
    model=settings.LLM_MODEL,
    api_key=settings.LLM_API_KEY,
    temperature=0
)

@tool 
def get_order(order_id: int) -> dict:
    """Get order information by order ID."""

    from app.core.database import SessionLocal
    from app.agents.tools.order_tools import (
        get_order as db_get_order
    )

    db = SessionLocal()

    try:
        result = db_get_order(
            db,
            order_id
        )
        return result or {
            "error": "Order not found"
        }
    finally:
        db.close()

@tool
def get_shipment(order_id: int) -> dict:
    """"Get shipment information for an order."""

    from app.core.database import SessionLocal
    from app.agents.tools.shipment_tools import (
        get_shipment as db_get_shipment
    )

    db = SessionLocal()

    try:
        result = db_get_shipment(
            db,
            order_id
        )

        return result or {
            "error": "Shipment not found"
        }

    finally:
        db.close()

@tool
def get_customer(customer_id: int) -> dict:
    """Get customer information."""

    from app.core.database import SessionLocal
    from app.agents.tools.customer_tools import (
        get_customer as db_get_customer,
    )

    db = SessionLocal()

    try:
        result = db_get_customer(
            db,
            customer_id,
        )

        return result or {
            "error": "Customer not found"
        }

    finally:
        db.close()

tools = [
    get_order,
    get_shipment,
    get_customer
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
"""

def agent_node(
    state: DelayedOrderState
):
    messages = state["messages"]

    response = llms_with_tools.invoke(
        [
            SystemMessage(
                content=SYSTEM_PROMPT
            )
        ]
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

    if current_iterations >= MAX_TOOL_ITERATIONS:
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
    tool_executor = ToolNode(tools)
    result = tool_executor.invoke(state)
    return {
        **result,
        "tool_iterations": current_iterations + 1
    }

DECISION_PROMPT = """
Based on the investigation above, produce the final operational decision.

Return ONLY valid JSON:

{
  "severity": "LOW | MEDIUM | HIGH | CRITICAL",
  "resolution": "TRACK_SHIPMENT | CONTACT_CARRIER | CONTACT_CUSTOMER | ESCALATE | NO_ACTION",
  "reasoning": "short explanation",
  "customer_message": "message or null",
  "requires_human": true
}

Do not invent information.
"""

def decision_node(
    state: DelayedOrderState
):
    response = llm.invoke(
        [
            SystemMessage(
                content=DECISION_PROMPT
            ),
            *state["messages"]
        ]
    )

    content = response.content

    if not isinstance(content, str):
        raise ValueError(
            "Unexpected LLM response format"
        )

    try:
        decision_data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid decision JSON: {content}"
        ) from exc

    decision = AgentDecision.model_validate(
        decision_data
    )

    return {
        "decision": decision.model_dump(),
        "required_human": decision.requires_human
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