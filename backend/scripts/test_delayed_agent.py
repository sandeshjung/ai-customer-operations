from app.agents.context import DelayedOrderContext
from app.agents.delayed_order_agent import (
    analyze_delayed_order,
)


context = DelayedOrderContext(
    order={
        "id": 10024,
        "customer_id": 8046,
        "status": "SHIPPED",
        "expected_delivery": "2026-08-16",
    },
    shipment={
        "tracking_number": "TRK123456",
        "status": "IN_TRANSIT",
        "carrier": "Example Carrier",
    },
    customer={
        "id": 8046,
        "name": "Test Customer",
        "email": "test@example.com",
    },
    delay_days=11,
)


decision = analyze_delayed_order(context)

print(decision.model_dump_json(indent=2))