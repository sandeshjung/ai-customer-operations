from decimal import Decimal

from app.models.customer import Customer
from app.models.product import Product


def test_customer_model():
    customer = Customer(
        name="Test User",
        email="test@example.com",
    )

    assert customer.name == "Test User"
    assert customer.email == "test@example.com"


def test_product_model():
    product = Product(
        name="Test Product",
        price=Decimal("99.99"),
    )

    assert product.name == "Test Product"
    assert product.price == Decimal("99.99")
