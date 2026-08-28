from sqlalchemy.orm import Session

from app.agents.tools.customer_tools import get_customer
from app.agents.tools.order_tools import get_order
from app.agents.tools.shipment_tools import get_shipment

class ToolRegistry:

    def __init__(self, db: Session):
        self.db = db

    def get_order(self, order_id: int) -> dict | None:
        return get_order(
            self.db,
            order_id
        )

    def get_customer(self, customer_id: int) -> dict | None:
        return get_customer(
            self.db,
            customer_id
        )

    def get_shipment(self, order_id: int) -> dict | None:
        return get_shipment(
            self.db,
            order_id
        )