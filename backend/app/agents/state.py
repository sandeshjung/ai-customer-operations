from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

class DelayedOrderState(TypedDict):

    messages: Annotated[
        list,
        add_messages
    ]

    order_id: int 

    order: dict | None
    shipment: dict | None
    customer: dict | None

    delay_days: int

    decision: dict | None

    requires_human: bool

    tool_iterations: int

    evidence: list[dict]