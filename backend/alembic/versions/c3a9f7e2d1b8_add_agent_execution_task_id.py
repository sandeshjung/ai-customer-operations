"""add agent execution task_id

Revision ID: c3a9f7e2d1b8
Revises: b7d3e5f1a2c4
Create Date: 2026-10-02 00:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3a9f7e2d1b8"
down_revision: str | Sequence[str] | None = "b7d3e5f1a2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "agent_executions", sa.Column("task_id", sa.String(length=100), nullable=True)
    )
    op.create_index(
        op.f("ix_agent_executions_task_id"),
        "agent_executions",
        ["task_id"],
        unique=False,
    )
    _backfill_task_ids()


# Subjects action_service gives the tickets that get sent to triage
# (ESCALATE / CONTACT_CUSTOMER) — how a pre-existing triage run is told apart
# from one on a customer-filed ticket.
_AGENT_TICKET_PREFIXES = ("ESCALATED: Delayed order", "Delayed order - ")


def _backfill_task_ids() -> None:
    """Delayed-order runs start their own task. A triage run on an
    agent-created ticket joins the latest earlier delayed-order run for that
    ticket's order; any other triage run is its own task."""
    conn = op.get_bind()
    runs = conn.execute(
        sa.text(
            "SELECT id, agent_name, event_id, input_data, created_at "
            "FROM agent_executions"
        )
    ).fetchall()

    delay_runs_by_order: dict[int, list] = {}
    for run in runs:
        if run.agent_name == "delayed_order_agent":
            order_id = _json(run.input_data).get("order_id")
            delay_runs_by_order.setdefault(order_id, []).append(run)

    for run in runs:
        task_id = run.event_id
        if run.agent_name == "triage_agent":
            ticket_id = _json(run.input_data).get("ticket_id")
            ticket = conn.execute(
                sa.text("SELECT subject, order_id FROM support_tickets WHERE id = :id"),
                {"id": ticket_id},
            ).first()
            if ticket and ticket.subject.startswith(_AGENT_TICKET_PREFIXES):
                earlier = [
                    d
                    for d in delay_runs_by_order.get(ticket.order_id, [])
                    if d.created_at <= run.created_at
                ]
                if earlier:
                    task_id = max(earlier, key=lambda d: d.created_at).event_id
        conn.execute(
            sa.text("UPDATE agent_executions SET task_id = :task WHERE id = :id"),
            {"task": task_id, "id": run.id},
        )


def _json(value) -> dict:
    if isinstance(value, str):
        return json.loads(value)
    return value or {}


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_agent_executions_task_id"), table_name="agent_executions")
    op.drop_column("agent_executions", "task_id")
