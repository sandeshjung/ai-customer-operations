import time
import uuid

from app.agents.graphs.delayed_order import delayed_order_graph
from app.agents.guardrails import validate_decision
from app.agents.prompts import build_delayed_order_investigation_message
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
                            order_id, delay_days
                        ),
                    }
                ],
                "order_id": order_id,
                "order": None,
                "shipment": None,
                "customer": None,
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
        order_id=order_id,
        input_data={"order_id": order_id, "delay_days": delay_days},
        decision=decision.model_dump(),
        model=settings.LLM_MODEL,
        input_tokens=result.get("llm_input_tokens", 0),
        output_tokens=result.get("llm_output_tokens", 0),
        total_tokens=result.get("llm_total_tokens", 0),
        llm_call_count=result.get("llm_call_count", 0),
        duration_ms=duration_ms,
        steps=extract_tool_steps(result.get("messages", [])),
    )

    db.add(execution)
    db.commit()

    return decision
