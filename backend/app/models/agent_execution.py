from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

class AgentExecution(Base):

    __tablename__ = "agent_executions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    agent_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    event_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    input_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    decision: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )