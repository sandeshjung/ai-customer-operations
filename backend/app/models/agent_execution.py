from datetime import datetime

from app.models.base import Base
from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)

    event_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # The unit of work this run belongs to, for per-task usage: the event_id
    # of the ORDER_DELAYED (or customer TICKET_CREATED) that started it. A
    # triage run on a ticket the delayed-order agent created shares its
    # task_id. Null on rows written before this column existed.
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # The order this run was about — set for both agents (triage via the
    # ticket's order_id), so an order's full agent history is one indexed
    # query instead of a scan over input_data JSON. Nullable: older rows and
    # tickets without an order.
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

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

    # Tool calls the agent made, in order: [{tool, args, result}]. Extracted
    # from the graph's message history after the run, for the admin
    # console's order timeline. Null for agents that don't call tools.
    steps: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
