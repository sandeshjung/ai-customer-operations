from sqlalchemy.orm import Session

from app.models.customer import Customer


def get_customer(
    db: Session,
    customer_id: int,
) -> dict | None:

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id)
        .first()
    )

    if not customer:
        return None

    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
    }