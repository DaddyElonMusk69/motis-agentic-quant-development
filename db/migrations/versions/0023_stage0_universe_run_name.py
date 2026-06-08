"""add stage0 universe run name

Revision ID: 0023_stage0_run_name
Revises: 0022_route_archive
Create Date: 2026-06-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0023_stage0_run_name"
down_revision = "0022_route_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stage0_universe_runs", sa.Column("name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("stage0_universe_runs", "name")
