"""add route manual sizing override flag

Revision ID: 0025_manual_sizing
Revises: 0024_exchange_aware_routes
Create Date: 2026-06-08
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0025_manual_sizing"
down_revision = "0024_exchange_aware_routes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deployment_routes", sa.Column("manual_sizing_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    _backfill_stage4_sizing()
    op.alter_column("deployment_routes", "manual_sizing_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("deployment_routes", "manual_sizing_enabled")


def _backfill_stage4_sizing() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        text(
            """
            select bundle_id, source_stage4_result_path, execution_setup
            from execution_bundles
            where status = 'promoted'
            """
        )
    ).mappings()
    for row in rows:
        setup = _as_mapping(row.get("execution_setup"))
        if _as_mapping(setup.get("sizing")):
            sizing = _as_mapping(setup["sizing"])
        else:
            sizing = _sizing_from_stage4(row.get("source_stage4_result_path"))
            if sizing:
                setup["sizing"] = sizing
                connection.execute(
                    text("update execution_bundles set execution_setup = :execution_setup where bundle_id = :bundle_id"),
                    {"execution_setup": json.dumps(setup), "bundle_id": row["bundle_id"]},
                )
        margin = _positive_number(sizing.get("margin_allocation_pct") if sizing else None)
        leverage = _positive_number(sizing.get("leverage") if sizing else None)
        if margin is None or leverage is None:
            continue
        connection.execute(
            text(
                """
                update deployment_routes
                set margin_allocation_pct = :margin_allocation_pct,
                    leverage = :leverage,
                    manual_sizing_enabled = false
                where active_bundle_id = :bundle_id
                """
            ),
            {"margin_allocation_pct": margin, "leverage": leverage, "bundle_id": row["bundle_id"]},
        )


def _sizing_from_stage4(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value:
        return {}
    path = Path(path_value)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    inputs = _as_mapping(payload.get("simulation_inputs"))
    margin = _positive_number(inputs.get("margin_allocation_pct"))
    leverage = _positive_number(inputs.get("leverage"))
    if margin is None or leverage is None:
        return {}
    return {
        "source": "stage4_realized_expectancy",
        "initial_capital_usdt": inputs.get("initial_capital_usdt"),
        "margin_allocation_pct": margin,
        "leverage": leverage,
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
