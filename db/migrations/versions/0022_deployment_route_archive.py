"""add deployment route archive state

Revision ID: 0022_route_archive
Revises: 0021_drop_signal_backlog
Create Date: 2026-06-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0022_route_archive"
down_revision = "0021_drop_signal_backlog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deployment_routes", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("deployment_routes", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("deployment_routes", "archived", server_default=None)


def downgrade() -> None:
    op.drop_column("deployment_routes", "archived_at")
    op.drop_column("deployment_routes", "archived")
