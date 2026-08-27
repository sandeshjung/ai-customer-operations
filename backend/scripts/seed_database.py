import random 
from datetime import date, datetime, timedelta
from decimal import Decimal

from faker import Faker
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.shipment import Shipment, ShipmentStatus

fake = Faker()

NUM_CUSTOMERS = 5000
NUM_PRODUCTS = 1000
NUM_ORDERS = 10000

def clear_database(db):
    db.execute(delete(Shipment))
    db.execute(delete(OrderItem))
    db.execute(delete(Order))
    db.execute(delete(Product))
    db.execute(delete(Customer))
    db.commit()

def create_customers(db):
    customers = []

    for _ in range(NUM_CUSTOMERS):
        customer = Customer(
            name=fake.name(),
            email=fake.unique.email(),
        )
        customers.append(customer)

    db.add_all(customers)
    db.flush()

    return customers

def create_products(db):
    products = []

    categories = [
        "Electronics",
        "Home",
        "Clothing",
        "Sports",
        "Books",
        "Accessories",
    ]

    for _ in range(NUM_PRODUCTS):
        category = random.choice(categories)

        product = Product(
            name=f"{fake.word().title()} {category}",
            description=fake.sentence(),
            price=Decimal(str(round(random.uniform(10, 1000), 2))
            ),
        )

        products.append(product)

    db.add_all(products)
    db.flush()

    return products

def create_orders(db, customers, products):
    orders = []

    today = date.today()

    for _ in range(NUM_ORDERS):
        customer = random.choice(customers)

        created_date = today - timedelta(
            days = random.randint(1, 60)
        )

        expected_delivery = created_date + timedelta(
            days = random.randint(3, 10)
        )

        order = Order(
            customer_id=customer.id,
            total_amount=Decimal("0.00"),
            status=random.choice(
                [
                    OrderStatus.CONFIRMED,
                    OrderStatus.PROCESSING,
                    OrderStatus.SHIPPED,
                    OrderStatus.DELIVERED,
                ]
            ),
            expected_delivery=expected_delivery,
            created_at=datetime.combine(created_date, datetime.min.time()),
        )

        db.add(order)
        db.flush()

        total = Decimal("0.00")

        for _ in range(random.randint(1, 4)):
            product = random.choice(products)
            quantity = random.randint(1, 3)

            item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=product.price,
            )

            total += product.price * quantity

            db.add(item)

        order.total_amount = total

        orders.append(order)

    db.flush()

    return orders

def create_shipments(db, orders):
    carriers = [
        "DHL",
        "FedEx",
        "UPS",
        "USPS",
    ]

    for order in orders:
        if order.status not in {
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED
        }:
            continue

        shipment_status = random.choice(
            [
                ShipmentStatus.IN_TRANSIT,
                ShipmentStatus.OUT_FOR_DELIVERY,
                ShipmentStatus.DELIVERED,
                ShipmentStatus.EXCEPTION
            ]
        )

        shipment = Shipment(
            order_id=order.id,
            carrier=random.choice(carriers),
            tracking_number=fake.unique.bothify(
                text="TRK-########"
            ),
            status=shipment_status,
            last_location=fake.city(),
            last_updated=datetime.utcnow() - timedelta(hours=random.randint(1, 120))
        )

        db.add(shipment)

def main():
    db = SessionLocal()

    try:
        print("Clearing database...")
        clear_database(db)

        print("Creating customers...")
        customers = create_customers(db)

        print("Creating products...")
        products = create_products(db)

        print("Creating orders...")
        orders = create_orders(
            db,
            customers,
            products
        )

        print("Creating shipments...")
        create_shipments(
            db,
            orders
        )

        db.commit()

        print("Database seeded successfully.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

if __name__ == "__main__":
    main()