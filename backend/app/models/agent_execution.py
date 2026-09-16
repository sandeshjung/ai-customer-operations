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

    # Usage/cost tracking — populated by agent_service.py / triage_service.py
    # from the LLM response's usage_metadata (see the AI usage monitor).
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    total_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    llm_call_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
