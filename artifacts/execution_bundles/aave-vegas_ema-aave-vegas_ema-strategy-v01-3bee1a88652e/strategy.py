from __future__ import annotations

from typing import Any


STRATEGY_ID = "aave-vegas_ema-strategy-v01"
STRATEGY_VERSION = "v0.1"


def decide(context: dict[str, Any]) -> dict[str, Any]:
    signal = context["signal"]
    payload = signal.get("payload", {})
    charts = payload.get("charts") or signal.get("charts", {})
    signal_id = signal["signal_id"]

    daily = _chart_stats(charts.get("1d", {}), lookback=10)
    anchor = _chart_stats(charts.get("2h", {}), lookback=6)
    eight_hour = _chart_stats(charts.get("8h", {}), lookback=6)
    four_hour = _chart_stats(charts.get("4h", {}), lookback=6)
    active_timeframes = payload.get("active_timeframes", signal.get("active_timeframes", []))
    interaction_distances = _interaction_distances(payload.get("interactions") or signal.get("interactions", []))

    if daily["return_pct"] is None and anchor["return_pct"] is None:
        return _decision(
            signal_id=signal_id,
            trade_action="SKIP",
            direction="FLAT",
            confidence=0.2,
            reason_code="missing_readable_chart_context",
            diagnostics={
                "has_1d": isinstance(charts.get("1d"), dict),
                "has_2h": isinstance(charts.get("2h"), dict),
            },
        )

    direction, reason_code, confidence = _select_direction(
        daily=daily,
        anchor=anchor,
        eight_hour=eight_hour,
        four_hour=four_hour,
        interaction_distances=interaction_distances,
    )

    return _decision(
        signal_id=signal_id,
        trade_action="ENTER",
        direction=direction,
        confidence=confidence,
        reason_code=reason_code,
        diagnostics={
            "active_timeframes": active_timeframes,
            "runtime_mode": context.get("runtime_mode", "backtest"),
            "daily_return_pct": daily["return_pct"],
            "daily_last_return_pct": daily["last_return_pct"],
            "daily_range_position_pct": daily["range_position_pct"],
            "daily_3bar_return_pct": daily["return_3bar_pct"],
            "daily_20bar_return_pct": daily["return_20bar_pct"],
            "anchor_return_pct": anchor["return_pct"],
            "anchor_last_return_pct": anchor["last_return_pct"],
            "anchor_range_position_pct": anchor["range_position_pct"],
            "anchor_3bar_return_pct": anchor["return_3bar_pct"],
            "anchor_10bar_return_pct": anchor["return_10bar_pct"],
            "eight_hour_5bar_return_pct": eight_hour["return_5bar_pct"],
            "four_hour_fast_tunnel_distance_pct": interaction_distances.get("4h_fast"),
            "two_hour_mid_tunnel_distance_pct": interaction_distances.get("2h_mid"),
        },
    )


def _select_direction(
    *,
    daily: dict[str, float | None],
    anchor: dict[str, float | None],
    eight_hour: dict[str, float | None],
    four_hour: dict[str, float | None],
    interaction_distances: dict[str, float],
) -> tuple[str, str, float]:
    daily_3bar = daily["return_3bar_pct"]
    anchor_10bar = anchor["return_10bar_pct"]
    eight_hour_5bar = eight_hour["return_5bar_pct"]
    anchor_return = anchor["return_pct"]
    anchor_3bar = anchor["return_3bar_pct"]
    anchor_last = anchor["last_return_pct"]
    anchor_range = anchor["range_position_pct"]
    daily_return = daily["return_pct"]
    daily_last = daily["last_return_pct"]
    daily_range = daily["range_position_pct"]
    daily_20bar = daily["return_20bar_pct"]
    fast_4h_distance = interaction_distances.get("4h_fast")
    mid_2h_distance = interaction_distances.get("2h_mid")

    if _lte(daily_3bar, -0.8745):
        if (
            _gte(daily_20bar, 0)
            and (anchor_10bar is None or _lte(anchor_10bar, -0.8))
            and (_lte(fast_4h_distance, 0.13) or _lte(mid_2h_distance, 0.15))
        ):
            return "LONG", "daily_pullback_with_tunnel_base", 0.66
        if _gt(anchor_3bar, 0.4) and (eight_hour_5bar is None or _lt(eight_hour_5bar, 0.5)):
            return "LONG", "daily_dip_with_anchor_reclaim", 0.65
        return "SHORT", "daily_three_bar_down_impulse_confirmed", 0.74

    if (
        _lte(daily_range, 30)
        and _lte(daily_20bar, -7)
        and _gte(daily_3bar, 0)
        and _gte(anchor_return, -0.75)
    ):
        return "LONG", "daily_washout_base_with_anchor_stabilization", 0.7

    if _lte(eight_hour_5bar, 1.9005):
        if _gt(anchor_10bar, 4.5278):
            return "SHORT", "overextended_2h_reclaim_into_soft_8h", 0.66
        if (
            _gte(anchor_range, 70)
            and _gte(daily_range, 7)
            and not (_lte(daily_range, 30) and _lte(daily_20bar, -12))
        ):
            return "SHORT", "muted_8h_relief_reclaim_at_anchor_high", 0.68
        if _lt(anchor_last, -0.9) and _lt(anchor_range, 30):
            return "SHORT", "muted_8h_anchor_rollover", 0.66
        return "LONG", "muted_8h_pressure_with_2h_reclaim", 0.72

    if _lte(fast_4h_distance, 0.1186):
        if _lte(anchor_3bar, -0.75) or (_lte(anchor_return, -0.5) and _lte(anchor_range, 25)):
            return "SHORT", "fast_4h_touch_with_2h_rollover", 0.68
        return "LONG", "fast_4h_tunnel_reclaim_confirmed", 0.72

    if _gt(anchor_return, 2.7261):
        if (
            _gte(anchor_range, 88)
            and _gte(daily_range, 40)
            and (eight_hour_5bar is None or _lt(eight_hour_5bar, 3.0))
            and not _gt(daily_20bar, 5)
        ):
            return "SHORT", "strong_2h_reclaim_high_range_exhaustion", 0.67
        if _lte(anchor_last, -0.1995):
            return "LONG", "strong_2h_reclaim_with_minor_pullback", 0.68
        return "LONG", "strong_2h_reclaim_follow_through", 0.76

    if _lte(mid_2h_distance, 0.0718):
        if _lte(anchor_3bar, -0.3384):
            if _gte(daily_range, 75) and _gt(daily_last, 2.0) and _gt(anchor_10bar, 1.0):
                return "LONG", "mid_tunnel_rollover_absorbed_by_daily_reversal", 0.64
            return "SHORT", "mid_tunnel_touch_with_2h_rollover", 0.66
        return "LONG", "mid_tunnel_touch_without_2h_rollover", 0.64

    if _gt(daily_last, 5.3269):
        return "LONG", "large_daily_reversal_overrides_anchor_softness", 0.62

    if _lte(daily_range, 30) and _lte(daily_20bar, -7) and _gte(daily_3bar, -0.5):
        return "LONG", "default_washout_base_override", 0.64

    return "SHORT", "8h_follow_through_with_weak_2h_reclaim", 0.71


def _chart_stats(chart: dict[str, Any], *, lookback: int) -> dict[str, float | None]:
    candles = chart.get("completed_candles", [])
    closes = [_close(candle, chart.get("columns", [])) for candle in candles]
    closes = [value for value in closes if value is not None]
    if len(closes) < 2:
        return {
            "return_pct": None,
            "last_return_pct": None,
            "range_position_pct": None,
            "return_3bar_pct": None,
            "return_5bar_pct": None,
            "return_10bar_pct": None,
            "return_20bar_pct": None,
        }

    start_index = max(0, len(closes) - lookback - 1)
    window = closes[-min(len(closes), lookback + 1) :]
    low = min(window)
    high = max(window)
    range_position_pct = ((closes[-1] - low) / (high - low) * 100) if high > low else 50.0
    return {
        "return_pct": _pct_change(closes[start_index], closes[-1]),
        "last_return_pct": _pct_change(closes[-2], closes[-1]),
        "range_position_pct": range_position_pct,
        "return_3bar_pct": _lagged_return(closes, 3),
        "return_5bar_pct": _lagged_return(closes, 5),
        "return_10bar_pct": _lagged_return(closes, 10),
        "return_20bar_pct": _lagged_return(closes, 20),
    }


def _interaction_distances(interactions: Any) -> dict[str, float]:
    distances: dict[str, float] = {}
    if not isinstance(interactions, list):
        return distances
    for interaction in interactions:
        if not isinstance(interaction, dict):
            continue
        timeframe = str(interaction.get("timeframe", "")).strip()
        tunnel = str(interaction.get("tunnel", "")).strip()
        if not timeframe or not tunnel:
            continue
        try:
            distances[f"{timeframe}_{tunnel}"] = abs(float(interaction["distance_pct"]) * 100)
        except (KeyError, TypeError, ValueError):
            continue
    return distances


def _close(candle: list[Any], columns: list[str]) -> float | None:
    try:
        close_index = columns.index("close") if "close" in columns else 4
        return float(candle[close_index])
    except (IndexError, TypeError, ValueError):
        return None


def _lagged_return(closes: list[float], bars: int) -> float | None:
    if len(closes) <= bars:
        return None
    return _pct_change(closes[-bars - 1], closes[-1])


def _pct_change(start: float | None, end: float | None) -> float | None:
    if start in (None, 0) or end is None:
        return None
    return (end / start - 1) * 100


def _lte(value: float | None, threshold: float) -> bool:
    return value is not None and value <= threshold


def _lt(value: float | None, threshold: float) -> bool:
    return value is not None and value < threshold


def _gte(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _gt(value: float | None, threshold: float) -> bool:
    return value is not None and value > threshold


def _decision(
    *,
    signal_id: str,
    trade_action: str,
    direction: str,
    confidence: float,
    reason_code: str,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "decision_id": f"{STRATEGY_ID}-{STRATEGY_VERSION}-{signal_id}",
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "signal_id": signal_id,
        "trade_action": trade_action,
        "action": trade_action,
        "direction": direction,
        "confidence": confidence,
        "reason_code": reason_code,
        "execution_profile": {},
        "diagnostics": diagnostics,
    }
