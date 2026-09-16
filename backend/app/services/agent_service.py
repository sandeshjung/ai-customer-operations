import time
import uuid

from app.agents.graphs.delayed_order import delayed_order_graph
from app.agents.guardrails import validate_decision
from app.core.config import settings
from app.core.logging import get_logger
from app.core.tracing import traced
from app.models.agent_execution import AgentExecution

logger = get_logger(__name__)


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
                        "content": (
                            f"Investigate delayed order "
                            f"{order_id}. "
                            f"It is {delay_days} days late."
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
        input_data={"order_id": order_id, "delay_days": delay_days},
        decision=decision.model_dump(),
        model=settings.LLM_MODEL,
        input_tokens=result.get("llm_input_tokens", 0),
        output_tokens=result.get("llm_output_tokens", 0),
        total_tokens=result.get("llm_total_tokens", 0),
        llm_call_count=result.get("llm_call_count", 0),
        duration_ms=duration_ms,
    )

    db.add(execution)
    db.commit()

    return decision
