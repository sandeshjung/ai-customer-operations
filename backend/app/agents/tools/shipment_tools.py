from app.models.shipment import Shipment
from sqlalchemy.orm import Session


def get_shipment(
    db: Session,
    order_id: int,
) -> dict | None:

    shipment = db.query(Shipment).filter(Shipment.order_id == order_id).first()

    if not shipment:
        return None

    return {
        "id": shipment.id,
        "order_id": shipment.order_id,
        "tracking_number": shipment.tracking_number,
        "status": shipment.status,
        "carrier": shipment.carrier,
    }
