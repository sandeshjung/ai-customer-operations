from app.agents.graphs.delayed_order import (
    delayed_order_graph,
)


result = delayed_order_graph.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Investigate delayed order 10024. "
                    "It is 11 days late."
                ),
            }
        ],
        "order_id": 10024,
        "order": None,
        "shipment": None,
        "customer": None,
        "delay_days": 11,
        "decision": None,
        "requires_human": False,
        "tool_iterations": 0,
    }
)

print("\nFINAL DECISION")
print(result["decision"])