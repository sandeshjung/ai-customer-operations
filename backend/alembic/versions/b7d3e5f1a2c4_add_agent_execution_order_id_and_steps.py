"""add agent execution order_id and steps

Revision ID: b7d3e5f1a2c4
Revises: 8f2c1a9d4b6e
Create Date: 2026-10-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d3e5f1a2c4"
down_revision: str | Sequence[str] | None = "8f2c1a9d4b6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "agent_executions", sa.Column("order_id", sa.Integer(), nullable=True)
    )
    op.create_index(
        op.f("ix_agent_executions_order_id"),
        "agent_executions",
        ["order_id"],
        unique=False,
    )
    op.add_column("agent_executions", sa.Column("steps", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("agent_executions", "steps")
    op.drop_index(op.f("ix_agent_executions_order_id"), table_name="agent_executions")
    op.drop_column("agent_executions", "order_id")
