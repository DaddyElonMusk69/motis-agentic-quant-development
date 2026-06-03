from quant_terminal_sdk.execution import DeploymentRoute, RiskLimits


def test_live_route_requires_promotion_data_warmup_and_manual_arm():
    route = DeploymentRoute(
        route_id="btc-vegas-live",
        strategy_id="vegas_reclaim",
        strategy_version="0.1.0",
        signal_engine_id="vegas_ema",
        signal_engine_version="0.1.0",
        asset="BTC",
        instrument="BTC-USDT-SWAP",
        account_mode="live",
        execution_adapter="okx",
        risk_limits=RiskLimits(max_notional_usd=250, max_daily_loss_usd=50),
        promoted=False,
        data_warmed=False,
        manually_armed=False,
        enabled=True,
    )

    assert route.can_execute_live() is False
    assert route.blockers() == [
        "route_not_promoted",
        "data_not_warmed",
        "route_not_manually_armed",
    ]


def test_promoted_warmed_and_armed_live_route_can_execute():
    route = DeploymentRoute(
        route_id="btc-vegas-live",
        strategy_id="vegas_reclaim",
        strategy_version="0.1.0",
        signal_engine_id="vegas_ema",
        signal_engine_version="0.1.0",
        asset="BTC",
        instrument="BTC-USDT-SWAP",
        account_mode="live",
        execution_adapter="okx",
        risk_limits=RiskLimits(max_notional_usd=250, max_daily_loss_usd=50),
        promoted=True,
        data_warmed=True,
        manually_armed=True,
        enabled=True,
    )

    assert route.can_execute_live() is True
    assert route.blockers() == []
