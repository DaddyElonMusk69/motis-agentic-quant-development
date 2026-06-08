"""drop route signal consumption backlog

Revision ID: 0021_drop_signal_backlog
Revises: 0020_owner_position_episodes
Create Date: 2026-06-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_drop_signal_backlog"
down_revision = "0020_owner_position_episodes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("route_signal_consumptions")


def downgrade() -> None:
    op.create_table(
        "route_signal_consumptions",
        sa.Column("consumption_id", sa.String(), nullable=False),
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("wake_id", sa.String(), nullable=False),
        sa.Column("signal_id", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("decision_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["deployment_routes.route_id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.signal_id"]),
        sa.ForeignKeyConstraint(["wake_id"], ["wake_runs.wake_id"]),
        sa.PrimaryKeyConstraint("consumption_id"),
        sa.UniqueConstraint("route_id", "signal_id"),
    )
