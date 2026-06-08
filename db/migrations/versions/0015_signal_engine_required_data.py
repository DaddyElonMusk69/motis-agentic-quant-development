"""add signal engine required data contract

Revision ID: 0015_signal_engine_required_data
Revises: 0014_live_execution_runtime
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_signal_engine_required_data"
down_revision = "0014_live_execution_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signal_engine_versions",
        sa.Column(
            "required_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("signal_engine_versions", "required_data", server_default=None)


def downgrade() -> None:
    op.drop_column("signal_engine_versions", "required_data")
