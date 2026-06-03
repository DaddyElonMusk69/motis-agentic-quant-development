from quant_terminal_api.db.models import metadata


def test_schema_declares_core_product_tables():
    expected = {
        "data_sources",
        "market_data_refs",
        "signal_engines",
        "signal_engine_versions",
        "signals",
        "strategy_modules",
        "strategy_versions",
        "walk_forward_templates",
        "walk_forward_runs",
        "stage_runs",
        "decisions",
        "score_summaries",
        "agent_tasks",
        "agent_runs",
        "deployment_routes",
        "audit_log",
    }

    assert expected.issubset(set(metadata.tables))


def test_deployment_routes_enforce_one_live_route_per_strategy_asset_pair():
    route_table = metadata.tables["deployment_routes"]

    unique_constraints = {
        tuple(constraint.columns.keys())
        for constraint in route_table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("strategy_id", "asset") in unique_constraints


def test_market_data_refs_unique_key_includes_data_origin():
    table = metadata.tables["market_data_refs"]

    unique_constraints = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("source_id", "instrument", "data_type", "timeframe", "data_origin", "ingestion_version") in unique_constraints
