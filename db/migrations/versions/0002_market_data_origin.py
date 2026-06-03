"""add market data origin

Revision ID: 0002_market_data_origin
Revises: 0001_initial_schema
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_market_data_origin"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

OLD_CONSTRAINT = "market_data_refs_source_id_instrument_data_type_timeframe_i_key"
NEW_CONSTRAINT = "uq_market_data_refs_identity_with_origin"


def upgrade() -> None:
    op.add_column(
        "market_data_refs",
        sa.Column("data_origin", sa.String(), nullable=False, server_default="raw"),
    )
    op.drop_constraint(OLD_CONSTRAINT, "market_data_refs", type_="unique")
    op.create_unique_constraint(
        NEW_CONSTRAINT,
        "market_data_refs",
        ["source_id", "instrument", "data_type", "timeframe", "data_origin", "ingestion_version"],
    )
    op.alter_column("market_data_refs", "data_origin", server_default=None)


def downgrade() -> None:
    op.drop_constraint(NEW_CONSTRAINT, "market_data_refs", type_="unique")
    op.create_unique_constraint(
        OLD_CONSTRAINT,
        "market_data_refs",
        ["source_id", "instrument", "data_type", "timeframe", "ingestion_version"],
    )
    op.drop_column("market_data_refs", "data_origin")
