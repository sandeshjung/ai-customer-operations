from app.agents.graphs.delayed_order import delayed_order_graph
from app.agents.guardrails import validate_decision
from app.models.agent_execution import AgentExecution
from app.agents.models import AgentDecision
from app.core.tracing import traced

import uuid
from app.core.logging import get_logger

logger = get_logger(__name__)

def investigate_delayed_order(
        db,
        order_id: int,
        delay_days: int,
        event_id: str
):
    execution_id = str(uuid.uuid4())
    logger.info(
        "Starting delayed order investigation",
        extra={
            "execution_id": execution_id,
            "order_id": order_id,
            "event_id": event_id,
        },
    )

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
                        )
                    }
                ],
                "order_id": order_id,
                "order": None,
                "shipment": None,
                "customer": None,
                "delay_days": delay_days,
                "decision": None,
                "requires_human": False,
                "tool_iterations": 0
            }
        )

        decision = validate_decision(
            result["decision"]
        )

        span.set_attribute("severity", decision.severity)
        span.set_attribute("resolution", decision.resolution)
        span.set_attribute("requires_human", decision.requires_human)

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
        input_data={
            "order_id": order_id,
            "delay_days": delay_days
        },
        decision=decision.model_dump()
    )

    db.add(execution)
    db.commit()

    return decision
