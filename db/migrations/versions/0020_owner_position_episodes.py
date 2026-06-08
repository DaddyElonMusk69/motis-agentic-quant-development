from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from quant_terminal_api.db.models import JSON_DOCUMENT


revision = "0020_owner_position_episodes"
down_revision = "0019_route_sizing_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("owner_states", sa.Column("position_instance_id", sa.String(), nullable=True))
    op.add_column("owner_states", sa.Column("position_state", JSON_DOCUMENT, nullable=False, server_default="{}"))
    op.alter_column("owner_states", "position_state", server_default=None)


def downgrade() -> None:
    op.drop_column("owner_states", "position_state")
    op.drop_column("owner_states", "position_instance_id")
