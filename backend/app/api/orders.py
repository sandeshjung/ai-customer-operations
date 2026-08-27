from datetime import UTC, datetime
from decimal import Decimal

from app.core.database import get_db

from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product

from app.schemas.delayed_order import DelayedOrderResponse
from app.schemas.order import OrderCreate, OrderResponse

from app.services.order_monitor import detect_delayed_orders

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get(
    "/delayed",
    response_model=list[DelayedOrderResponse],
)
def get_delayed_orders(
    db: Session = Depends(get_db),
):
    today = datetime.now(UTC).date()

    orders = (
        db.query(Order)
        .options(selectinload(Order.shipment))
        .filter(
            Order.expected_delivery.is_not(None),
            Order.expected_delivery < today,
            Order.status.notin_(
                [
                    OrderStatus.DELIVERED,
                    OrderStatus.CANCELLED,
                    OrderStatus.REFUNDED,
                ]
            ),
        )
        .all()
    )

    results = []

    for order in orders:
        delay_days = (today - order.expected_delivery).days

        shipment = order.shipment

        results.append(
            DelayedOrderResponse(
                order_id=order.id,
                customer_id=order.customer_id,
                expected_delivery=order.expected_delivery,
                delay_days=delay_days,
                shipment_status=(shipment.status.value if shipment else None),
                tracking_number=(shipment.tracking_number if shipment else None),
            )
        )

        return results


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .options(
            selectinload(Order.items),
            selectinload(Order.shipment),
        )
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    return order


@router.post(
    "",
    response_model=OrderResponse,
)
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
):
    from app.models.customer import Customer

    customer = db.get(Customer, data.customer_id)

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    if not data.items:
        raise HTTPException(
            status_code=400,
            detail="Order must have at least one item",
        )

    order = Order(
        customer_id=data.customer_id,
        expected_delivery=data.expected_delivery,
        total_amount=Decimal("0.00"),
    )

    db.add(order)

    total = Decimal("0.00")

    for item_data in data.items:
        product = db.get(Product, item_data.product_id)

        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product with id {item_data.product_id} not found",
            )

        if item_data.quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity must be greater than 0",
            )

        item = OrderItem(
            order=order,
            product=product,
            quantity=item_data.quantity,
            unit_price=product.price,
        )

        total += product.price * item_data.quantity

        db.add(item)

    order.total_amount = total

    db.commit()
    db.refresh(order)
    return order


@router.post("/monitor/delayed")
def monitor_delayed_orders(db: Session = Depends(get_db)):
    published = detect_delayed_orders(db)

    return {
        "published_events": published
    }