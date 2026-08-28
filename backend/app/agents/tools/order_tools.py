from sqlalchemy.orm import Session

from app.models.order import Order

def get_order(
        db: Session,
        order_id: int,
) -> dict | None:

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        return None

    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "status": order.status,
        "expected_salary": (
            order.expected_delivery.isoformat()
            if order.expected_delivery
            else None
        )
    }