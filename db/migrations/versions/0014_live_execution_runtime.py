"""add live execution runtime tables

Revision ID: 0014_live_execution_runtime
Revises: 0013_two_window_walk_forward
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_live_execution_runtime"
down_revision = "0013_two_window_walk_forward"
branch_labels = None
depends_on = None

JSON_DOCUMENT = postgresql.JSONB


def upgrade() -> None:
    op.create_table(
        "execution_bundles",
        sa.Column("bundle_id", sa.String(), nullable=False),
        sa.Column("asset", sa.String(), nullable=False),
        sa.Column("instrument", sa.String(), nullable=False),
        sa.Column("signal_engine_id", sa.String(), nullable=False),
        sa.Column("signal_engine_version", sa.String(), nullable=False),
        sa.Column("strategy_id", sa.String(), nullable=False),
        sa.Column("strategy_version", sa.String(), nullable=False),
        sa.Column("source_stage1_session_id", sa.String(), nullable=False),
        sa.Column("source_stage4_result_path", sa.Text(), nullable=False),
        sa.Column("bundle_uri", sa.Text(), nullable=False),
        sa.Column("strategy_module_ref", sa.Text(), nullable=False),
        sa.Column("execution_setup", JSON_DOCUMENT(), nullable=False),
        sa.Column("risk_limits", JSON_DOCUMENT(), nullable=False),
        sa.Column("evidence_refs", JSON_DOCUMENT(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["source_stage1_session_id"], ["stage1_research_sessions.session_id"]),
        sa.PrimaryKeyConstraint("bundle_id"),
        sa.UniqueConstraint("content_hash"),
    )
    op.add_column("deployment_routes", sa.Column("active_bundle_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "deployment_routes_active_bundle_id_fkey",
        "deployment_routes",
        "execution_bundles",
        ["active_bundle_id"],
        ["bundle_id"],
    )
    op.drop_constraint("deployment_routes_strategy_id_asset_key", "deployment_routes", type_="unique")
    op.create_unique_constraint(
        "deployment_routes_asset_signal_engine_account_key",
        "deployment_routes",
        ["asset", "signal_engine_id", "account_mode"],
    )

    op.create_table(
        "wake_runs",
        sa.Column("wake_id", sa.String(), nullable=False),
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("bundle_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("branch", sa.String(), nullable=False),
        sa.Column("blockers", JSON_DOCUMENT(), nullable=False),
        sa.Column("exchange_snapshot", JSON_DOCUMENT(), nullable=False),
        sa.Column("signal_scan_result", JSON_DOCUMENT(), nullable=False),
        sa.Column("strategy_decision", JSON_DOCUMENT(), nullable=False),
        sa.Column("order_intents", JSON_DOCUMENT(), nullable=False),
        sa.Column("adapter_results", JSON_DOCUMENT(), nullable=False),
        sa.Column("error", JSON_DOCUMENT(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["bundle_id"], ["execution_bundles.bundle_id"]),
        sa.ForeignKeyConstraint(["route_id"], ["deployment_routes.route_id"]),
        sa.PrimaryKeyConstraint("wake_id"),
    )
    op.create_table(
        "owner_states",
        sa.Column("owner_state_id", sa.String(), nullable=False),
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("bundle_id", sa.String(), nullable=False),
        sa.Column("asset", sa.String(), nullable=False),
        sa.Column("instrument", sa.String(), nullable=False),
        sa.Column("account_mode", sa.String(), nullable=False),
        sa.Column("owner_strategy_id", sa.String(), nullable=False),
        sa.Column("owner_strategy_version", sa.String(), nullable=False),
        sa.Column("opened_from_signal_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["bundle_id"], ["execution_bundles.bundle_id"]),
        sa.ForeignKeyConstraint(["route_id"], ["deployment_routes.route_id"]),
        sa.PrimaryKeyConstraint("owner_state_id"),
    )
    op.create_table(
        "route_signal_consumptions",
        sa.Column("consumption_id", sa.String(), nullable=False),
        sa.Column("route_id", sa.String(), nullable=False),
        sa.Column("wake_id", sa.String(), nullable=False),
        sa.Column("signal_id", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("decision_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["deployment_routes.route_id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.signal_id"]),
        sa.ForeignKeyConstraint(["wake_id"], ["wake_runs.wake_id"]),
        sa.PrimaryKeyConstraint("consumption_id"),
        sa.UniqueConstraint("route_id", "signal_id"),
    )


def downgrade() -> None:
    op.drop_table("route_signal_consumptions")
    op.drop_table("owner_states")
    op.drop_table("wake_runs")
    op.drop_constraint("deployment_routes_asset_signal_engine_account_key", "deployment_routes", type_="unique")
    op.drop_constraint("deployment_routes_active_bundle_id_fkey", "deployment_routes", type_="foreignkey")
    op.drop_column("deployment_routes", "active_bundle_id")
    op.create_unique_constraint("deployment_routes_strategy_id_asset_key", "deployment_routes", ["strategy_id", "asset"])
    op.drop_table("execution_bundles")
