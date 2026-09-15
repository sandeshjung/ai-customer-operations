from datetime import datetime

from app.models.base import Base
from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)

    event_id: Mapped[str] = mapped_column(String(100), nullable=False)

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
