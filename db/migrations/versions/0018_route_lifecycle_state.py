"""add deployment route lifecycle state

Revision ID: 0018_route_lifecycle_state
Revises: 0017_route_settings
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_route_lifecycle_state"
down_revision = "0017_route_settings"
branch_labels = None
depends_on = None

JSON_DOCUMENT = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column(
        "deployment_routes",
        sa.Column("scheduler_status", sa.String(), nullable=False, server_default="stopped"),
    )
    op.add_column(
        "deployment_routes",
        sa.Column("auto_submit_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("deployment_routes", sa.Column("last_wake_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deployment_routes", sa.Column("last_wake_id", sa.String(), nullable=True))
    op.add_column("deployment_routes", sa.Column("next_wake_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "deployment_routes",
        sa.Column("last_lifecycle_error", JSON_DOCUMENT, nullable=False, server_default="{}"),
    )
    op.alter_column("deployment_routes", "scheduler_status", server_default=None)
    op.alter_column("deployment_routes", "auto_submit_enabled", server_default=None)
    op.alter_column("deployment_routes", "last_lifecycle_error", server_default=None)


def downgrade() -> None:
    op.drop_column("deployment_routes", "last_lifecycle_error")
    op.drop_column("deployment_routes", "next_wake_at")
    op.drop_column("deployment_routes", "last_wake_id")
    op.drop_column("deployment_routes", "last_wake_at")
    op.drop_column("deployment_routes", "auto_submit_enabled")
    op.drop_column("deployment_routes", "scheduler_status")
