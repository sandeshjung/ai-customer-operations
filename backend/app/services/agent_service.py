from app.agents.graphs.delayed_order import delayed_order_graph
from app.agents.guardrails import validate_decision
from app.models.agent_execution import AgentExecution

def investigate_delayed_order(
        db,
        order_id: int,
        delay_days: int,
        event_id: str
):
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
    db.commit

    return decision