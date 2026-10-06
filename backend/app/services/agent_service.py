import json
import time
import uuid

from app.agents.graphs.delayed_order import delayed_order_graph
from app.agents.guardrails import validate_decision
from app.agents.prompts import build_delayed_order_investigation_message
from app.agents.tools.customer_tools import get_customer
from app.agents.tools.order_tools import get_order
from app.agents.tools.shipment_tools import get_shipment
from app.core.config import settings
from app.core.logging import get_logger
from app.core.tracing import traced
from app.models.agent_execution import AgentExecution

logger = get_logger(__name__)

# Tool results can be large (policy chunks) — keep the timeline payload small.
MAX_STEP_RESULT_CHARS = 1500


def extract_tool_steps(messages: list) -> list[dict]:
    """Pairs each tool call the LLM requested with the result it got back,
    in call order, from the graph's final message history."""
    steps: list[dict] = []
    by_call_id: dict[str, dict] = {}

    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            step = {"tool": call.get("name"), "args": call.get("args"), "result": None}
            steps.append(step)
            if call.get("id"):
                by_call_id[call["id"]] = step

        call_id = getattr(message, "tool_call_id", None)
        if call_id and call_id in by_call_id:
            content = message.content
            if not isinstance(content, str):
                content = str(content)
            by_call_id[call_id]["result"] = content[:MAX_STEP_RESULT_CHARS]

    return steps


def prefetch_order_records(db, order_id: int) -> tuple[dict, list[dict]]:
    """Loads the order, shipment and customer the agent always needs, so it
    doesn't spend an LLM round trip on each lookup (the agent used to fetch
    them one tool call per turn — about 4 of a run's 6-7 LLM calls).

    Returns the records for the first message, plus timeline steps in the
    same shape extract_tool_steps() produces, marked as prefetched.
    """
    order = get_order(db, order_id)
    shipment = get_shipment(db, order_id)
    customer_record = get_customer(db, order["customer_id"]) if order else None
    # The agent needs the name for the customer message; the email address
    # isn't needed to decide anything, so it isn't sent to the LLM.
    customer = (
        {"id": customer_record["id"], "name": customer_record["name"]}
        if customer_record
        else None
    )

    records = {"order": order, "shipment": shipment, "customer": customer}
    steps = [
        {"tool": "get_order", "args": {"order_id": order_id}, "result": order},
        {"tool": "get_shipment", "args": {"order_id": order_id}, "result": shipment},
    ]
    if order:
        steps.append(
            {
                "tool": "get_customer",
                "args": {"customer_id": order["customer_id"]},
                "result": customer,
            }
        )
    for step in steps:
        step["result"] = json.dumps(step["result"] or {"error": "not found"})[
            :MAX_STEP_RESULT_CHARS
        ]
        step["prefetched"] = True
    return records, steps


def investigate_delayed_order(db, order_id: int, delay_days: int, event_id: str):
    execution_id = str(uuid.uuid4())
    logger.info(
        "Starting delayed order investigation",
        extra={
            "execution_id": execution_id,
            "order_id": order_id,
            "event_id": event_id,
        },
    )

    start_time = time.perf_counter()

    records, prefetched_steps = prefetch_order_records(db, order_id)

    with traced(
        "delayed_order_agent.run",
        tracer_name="delayed_order_agent",
        order_id=order_id,
        delay_days=delay_days,
        event_id=event_id,
        execution_id=execution_id,
    ) as span:
        result = delayed_order_graph.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": build_delayed_order_investigation_message(
                            order_id, delay_days, **records
                        ),
                    }
                ],
                "order_id": order_id,
                **records,
                "delay_days": delay_days,
                "decision": None,
                "requires_human": False,
                "tool_iterations": 0,
                "llm_input_tokens": 0,
                "llm_output_tokens": 0,
                "llm_total_tokens": 0,
                "llm_call_count": 0,
            }
        )

        decision = validate_decision(result["decision"])

        span.set_attribute("severity", decision.severity)
        span.set_attribute("resolution", decision.resolution)
        span.set_attribute("requires_human", decision.requires_human)

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    logger.info(
        "Delayed order investigation completed",
        extra={
            "order_id": order_id,
            "event_id": event_id,
            "severity": decision.severity,
            "resolution": decision.resolution,
            "requires_human": decision.requires_human,
            "evidence": decision.evidence,
            "trace_id": decision.trace_id,
        },
    )
    execution = AgentExecution(
        agent_name="delayed_order_agent",
        event_id=event_id,
        task_id=event_id,
        order_id=order_id,
        input_data={"order_id": order_id, "delay_days": delay_days},
        decision=decision.model_dump(),
        model=settings.LLM_MODEL,
        input_tokens=result.get("llm_input_tokens", 0),
        output_tokens=result.get("llm_output_tokens", 0),
        total_tokens=result.get("llm_total_tokens", 0),
        llm_call_count=result.get("llm_call_count", 0),
        duration_ms=duration_ms,
        steps=prefetched_steps + extract_tool_steps(result.get("messages", [])),
    )

    db.add(execution)
    db.commit()

    return decision
