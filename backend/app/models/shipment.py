from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ShipmentStatus(str, Enum):
    LABEL_CREATED = "LABEL_CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    EXCEPTION = "EXCEPTION"
    LOST = "LOST"


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    carrier: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    tracking_number: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    status: Mapped[ShipmentStatus] = mapped_column(
        String(30),
        nullable=False,
    )

    last_location: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    last_updated: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    order = relationship(
        "Order",
        back_populates="shipment",
    )