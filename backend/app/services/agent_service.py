from app.agents.graphs.delayed_order import delayed_order_graph
from app.agents.guardrails import validate_decision
from app.models.agent_execution import AgentExecution

import uuid
from app.core.logging import get_logger

execution_id = str(uuid.uuid4())
logger = get_logger(__name__)

def investigate_delayed_order(
        db,
        order_id: int,
        delay_days: int,
        event_id: str
):
    logger.info(
        "Starting delayed order investigation",
        extra={
            "execution_id": execution_id,
            "order_id": order_id,
            "event_id": event_id,
        },
    )
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

    logger.info(
        "Delayed order investigation completed",
        extra={
            "order_id": order_id,
            "event_id": event_id,
            "severity": decision.severity,
            "resolution": decision.resolution,
            "requires_human": decision.requires_human,
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