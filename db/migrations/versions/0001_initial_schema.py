"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op

from quant_terminal_api.db.models import metadata

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind())
