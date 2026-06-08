from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0019_route_sizing_controls"
down_revision = "0018_route_lifecycle_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deployment_routes", sa.Column("margin_allocation_pct", sa.Float(), nullable=False, server_default="10"))
    op.add_column("deployment_routes", sa.Column("leverage", sa.Float(), nullable=False, server_default="1"))
    op.alter_column("deployment_routes", "margin_allocation_pct", server_default=None)
    op.alter_column("deployment_routes", "leverage", server_default=None)


def downgrade() -> None:
    op.drop_column("deployment_routes", "leverage")
    op.drop_column("deployment_routes", "margin_allocation_pct")
