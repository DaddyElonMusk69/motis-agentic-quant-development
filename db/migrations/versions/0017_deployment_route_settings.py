"""add deployment route execution settings

Revision ID: 0017_route_settings
Revises: 0016_asset_account_routes
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_route_settings"
down_revision = "0016_asset_account_routes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deployment_routes",
        sa.Column("exchange_account", sa.String(), nullable=False, server_default="default"),
    )
    op.add_column(
        "deployment_routes",
        sa.Column("cron_interval_minutes", sa.Integer(), nullable=False, server_default="15"),
    )
    op.alter_column("deployment_routes", "exchange_account", server_default=None)
    op.alter_column("deployment_routes", "cron_interval_minutes", server_default=None)


def downgrade() -> None:
    op.drop_column("deployment_routes", "cron_interval_minutes")
    op.drop_column("deployment_routes", "exchange_account")
