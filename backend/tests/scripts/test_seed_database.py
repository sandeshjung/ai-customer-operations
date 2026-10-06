import sys
from pathlib import Path

from app.models.customer import Customer
from app.models.human_approval import HumanApproval
from app.models.notification import Notification
from app.models.order import Order
from app.models.support_ticket import SupportTicket, TicketPriority, TicketStatus
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from seed_database import clear_database


def test_clear_database_succeeds_after_agents_have_run(db_session):
    """Regression test: clear_database deleted orders and customers while
    tickets, approvals and notifications still referenced them, so
    `make seed` failed with a foreign-key violation once the agents had run."""
    # SQLite only enforces FKs when asked; Postgres always does.
    db_session.execute(text("PRAGMA foreign_keys=ON"))

    customer = Customer(name="Seeded", email="seeded@example.com")
    db_session.add(customer)
    db_session.commit()
    order = Order(customer_id=customer.id, total_amount=10, expected_delivery=None)
    db_session.add(order)
    db_session.commit()
    db_session.add_all(
        [
            SupportTicket(
                customer_id=customer.id,
                order_id=order.id,
                subject="Late",
                message="Late",
                priority=TicketPriority.MEDIUM,
                status=TicketStatus.OPEN,
            ),
            HumanApproval(
                event_id="evt-seed",
                order_id=order.id,
                customer_id=customer.id,
                agent_name="delayed_order_agent",
                decision={},
            ),
            Notification(
                customer_id=customer.id,
                order_id=order.id,
                channel="email",
                recipient="seeded@example.com",
                content="Hi",
            ),
        ]
    )
    db_session.commit()

    clear_database(db_session)

    assert db_session.query(Order).count() == 0
    assert db_session.query(Customer).count() == 0
    assert db_session.query(SupportTicket).count() == 0
