"""make deployment routes exchange aware

Revision ID: 0024_exchange_aware_routes
Revises: 0023_stage0_run_name
Create Date: 2026-06-08
"""

from __future__ import annotations

from alembic import op

revision = "0024_exchange_aware_routes"
down_revision = "0023_stage0_run_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("deployment_routes_asset_account_key", "deployment_routes", type_="unique")
    op.create_unique_constraint(
        "deployment_routes_asset_account_exchange_key",
        "deployment_routes",
        ["asset", "account_mode", "execution_adapter", "exchange_account"],
    )


def downgrade() -> None:
    op.drop_constraint("deployment_routes_asset_account_exchange_key", "deployment_routes", type_="unique")
    op.create_unique_constraint(
        "deployment_routes_asset_account_key",
        "deployment_routes",
        ["asset", "account_mode"],
    )
