from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload
from decimal import Decimal

from app.core.database import get_db
from app.models.order import Order
from app.schemas.order import OrderResponse

from app.models.order_item import OrderItem
from app.models.product import Product
from app.schemas.order import OrderCreate

router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)

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
                detail=f"Quantity must be greater than 0",
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