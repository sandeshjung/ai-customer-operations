from app.models.customer import Customer
from app.models.product import Product
from sqlalchemy.orm import Session


def seed_basic_data(db: Session):
    customer = Customer(
        name="Demo Customer",
        email="demo@example.com",
    )

    product = Product(
        name="Wireless Headphones",
        description="High-quality wireless headphones with noise cancellation.",
        price=99.99,
    )

    db.add(customer)
    db.add(product)
    db.commit()
