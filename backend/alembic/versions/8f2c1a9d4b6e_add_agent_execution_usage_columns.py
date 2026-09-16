"""add agent execution usage columns

Revision ID: 8f2c1a9d4b6e
Revises: 6ad880be9a88
Create Date: 2026-09-16 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f2c1a9d4b6e"
down_revision: str | Sequence[str] | None = "6ad880be9a88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "agent_executions", sa.Column("model", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "agent_executions",
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_executions",
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_executions",
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_executions",
        sa.Column("llm_call_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_executions", sa.Column("duration_ms", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("agent_executions", "duration_ms")
    op.drop_column("agent_executions", "llm_call_count")
    op.drop_column("agent_executions", "total_tokens")
    op.drop_column("agent_executions", "output_tokens")
    op.drop_column("agent_executions", "input_tokens")
    op.drop_column("agent_executions", "model")
