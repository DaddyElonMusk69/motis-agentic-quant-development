"""scope deployment routes to asset and account

Revision ID: 0016_asset_account_routes
Revises: 0015_signal_engine_required_data
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op

revision = "0016_asset_account_routes"
down_revision = "0015_signal_engine_required_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM deployment_routes
                GROUP BY asset, account_mode
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'cannot scope deployment_routes to asset/account while duplicate asset/account routes exist';
            END IF;
        END $$;
        """
    )
    op.drop_constraint("deployment_routes_asset_signal_engine_account_key", "deployment_routes", type_="unique")
    op.create_unique_constraint(
        "deployment_routes_asset_account_key",
        "deployment_routes",
        ["asset", "account_mode"],
    )


def downgrade() -> None:
    op.drop_constraint("deployment_routes_asset_account_key", "deployment_routes", type_="unique")
    op.create_unique_constraint(
        "deployment_routes_asset_signal_engine_account_key",
        "deployment_routes",
        ["asset", "signal_engine_id", "account_mode"],
    )
