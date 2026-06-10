"""add async jobs table

Revision ID: 0026_jobs
Revises: 0025_manual_sizing
Create Date: 2026-06-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_jobs"
down_revision = "0025_manual_sizing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("scope_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_step", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("locked_by", sa.String(), nullable=True),
        sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index("ix_jobs_scope_key", "jobs", ["scope_key"])
    op.create_index("ix_jobs_status_priority_created", "jobs", ["status", "priority", "created_at"])
    op.create_index(
        "ux_jobs_active_scope",
        "jobs",
        ["scope_key"],
        unique=True,
        postgresql_where=sa.text("status in ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("ux_jobs_active_scope", table_name="jobs")
    op.drop_index("ix_jobs_status_priority_created", table_name="jobs")
    op.drop_index("ix_jobs_scope_key", table_name="jobs")
    op.drop_table("jobs")
